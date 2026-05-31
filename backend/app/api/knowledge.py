from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.knowledge.embeddings import EmbeddingService
from app.services.knowledge.graph import KnowledgeGraph
from app.services.knowledge.notes import NotesService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
from structlog import get_logger

logger = get_logger(__name__)
graph = KnowledgeGraph()
notes_service = NotesService()
embedder = EmbeddingService()


class NoteCreate(BaseModel):
    title: str
    content: str
    entity_type: str | None = None
    entity_id: str | None = None


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class SearchQuery(BaseModel):
    query: str
    repo_id: str | None = None
    entity_type: str | None = None
    language: str | None = None
    limit: int = 10


# ─── Semantic Search ─────────────────────────────────────

@router.post("/search")
async def semantic_search(payload: SearchQuery, db: AsyncSession = Depends(get_db)):
    results = await embedder.search(
        db,
        query=payload.query,
        repo_id=payload.repo_id,
        entity_type=payload.entity_type,
        language=payload.language,
        limit=payload.limit,
    )
    return {"query": payload.query, "results": results, "count": len(results)}


# ─── Graph Queries ───────────────────────────────────────

@router.get("/graph/owner")
async def find_owner(repo_id: str, file_path: str):
    owner = await graph.find_owner(repo_id, file_path)
    if not owner:
        raise HTTPException(status_code=404, detail="No owner found")
    return owner


@router.get("/graph/dependents")
async def find_dependents(repo_id: str, entity_name: str):
    deps = await graph.find_dependents(repo_id, entity_name)
    return {"entity": entity_name, "dependents": deps, "count": len(deps)}


@router.get("/graph/dependencies")
async def find_dependencies(repo_id: str, entity_name: str):
    deps = await graph.find_dependencies(repo_id, entity_name)
    return {"entity": entity_name, "dependencies": deps, "count": len(deps)}


@router.get("/graph/architecture")
async def get_architecture(repo_id: str):
    arch = await graph.get_architecture(repo_id)
    return {"repo_id": repo_id, "modules": arch}


@router.get("/graph/module-graph")
async def get_module_graph(repo_id: str):
    data = await graph.get_module_graph(repo_id)
    return data


@router.get("/graph/search")
async def search_graph(query: str, limit: int = 20):
    results = await graph.search_graph(query, limit)
    return {"query": query, "results": results}


@router.get("/concepts")
async def list_concepts(db: AsyncSession = Depends(get_db)):
    """Concept cards for the Knowledge page. Reads from the `concepts` table
    that `ConceptExtractor` writes — each row has a real LLM-authored
    summary, file count, ref count, and an experts list resolved to actual
    contributors. Empty when no repo has been processed yet; the frontend
    surfaces a "Generate concepts" CTA in that case."""
    from app.models.concept import Concept
    from app.models.repo import Repo
    from sqlalchemy import select as sa_select

    rows = (
        await db.execute(
            sa_select(Concept, Repo.local_name)
            .join(Repo, Repo.id == Concept.repo_id, isouter=True)
            .order_by(Concept.cat.asc(), Concept.files.desc(), Concept.name.asc())
        )
    ).all()

    concepts = []
    for c, repo_name in rows:
        concepts.append({
            "id": str(c.id),
            "name": c.name,
            "cat": c.cat,
            "summary": c.summary,
            "files": c.files,
            "refs": c.refs,
            "experts": c.experts or [],
            "repo": repo_name,
            "repo_id": c.repo_id,
            "generated_at": str(c.generated_at) if c.generated_at else None,
        })

    return {"concepts": concepts, "count": len(concepts)}


@router.post("/concepts/generate")
async def generate_concepts(
    db: AsyncSession = Depends(get_db), repo_id: str | None = None
):
    """Run the LLM concept extractor. Pass `?repo_id=<id>` to scope to one
    repo, omit to process every active repo. Returns per-repo counts."""
    from app.services.agent.concept_extractor import ConceptExtractor

    extractor = ConceptExtractor(graph)
    if repo_id:
        produced = await extractor.extract_for_repo(db, repo_id)
        return {"repo_id": repo_id, "count": len(produced), "concepts": produced}
    summary = await extractor.extract_for_all(db)
    total = sum(summary.values())
    return {"by_repo": summary, "count": total}


@router.get("/graph/stats")
async def get_graph_stats():
    """Aggregate node counts across the knowledge graph. The dashboard uses
    `concepts` (sum of File + Module + Function + Class) for the hero sentence."""
    return await graph.get_stats()


@router.get("/contributors")
async def list_contributors():
    """The team, read from the knowledge graph: every profiled contributor with
    the files/repos/languages they own (built from commit history)."""
    contributors = await graph.list_contributors()
    return {"contributors": contributors, "count": len(contributors)}


@router.get("/suggested-questions")
async def suggested_questions(repo_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """Grounded starter questions for the dashboard ask box, derived from real
    data about the active repo (its name, whether it has PRs, its most-populated
    module, whether the graph knows any contributors). Returns ``[]`` when no
    repo is onboarded yet, so the UI shows a setup hint instead of fake repos."""
    from sqlalchemy import func, select as sa_select

    from app.models.code_embedding import CodeEmbedding
    from app.models.pr import PR
    from app.models.repo import Repo
    from app.services.knowledge.suggested_questions import build_suggested_questions

    repo_q = sa_select(Repo).where(Repo.is_active == True)  # noqa: E712
    if repo_id:
        repo_q = repo_q.where(Repo.id == repo_id)
    repo = (await db.execute(repo_q.limit(1))).scalars().first()
    if repo is None:
        return {"repo": None, "questions": []}

    has_prs = bool((await db.execute(
        sa_select(func.count(PR.id)).where(PR.repo_id == repo.id)
    )).scalar() or 0)

    # Most-populated top-level directory in the embedded code = a real module to
    # ask about. Restrict to paths with a "/" so we get a directory, not a
    # loose top-level file.
    dir_expr = func.split_part(CodeEmbedding.file_path, "/", 1)
    top_row = (await db.execute(
        sa_select(dir_expr.label("dir"), func.count())
        .where(CodeEmbedding.repo_id == repo.id, CodeEmbedding.file_path.like("%/%"))
        .group_by(dir_expr)
        .order_by(func.count().desc())
        .limit(1)
    )).first()
    top_module = top_row[0] if top_row and top_row[0] else None

    # Best-effort: a Neo4j blip must not break the dashboard, so a failed
    # contributors lookup simply drops that one question.
    has_contributors = False
    try:
        has_contributors = len(await graph.list_contributors(limit=1)) > 0
    except Exception as e:
        logger.warning("suggested_questions_contributors_failed", error=str(e)[:120])

    questions = build_suggested_questions(
        repo.local_name,
        has_prs=has_prs,
        top_module=top_module,
        has_contributors=has_contributors,
    )
    return {"repo": repo.local_name, "questions": questions}


# ─── Notes ───────────────────────────────────────────────

@router.get("/notes")
async def list_notes(db: AsyncSession = Depends(get_db), limit: int = 50):
    notes = await notes_service.list_notes(db, limit=limit)
    return {"notes": [{"id": n.id, "title": n.title, "entity_type": n.entity_type,
                        "entity_id": n.entity_id, "updated_at": str(n.updated_at)} for n in notes]}


@router.post("/notes", status_code=201)
async def create_note(payload: NoteCreate, db: AsyncSession = Depends(get_db)):
    note = await notes_service.create(
        db, payload.title, payload.content, payload.entity_type, payload.entity_id
    )
    await graph.create_note_node(str(note.id), note.title, payload.entity_id)
    return {"id": str(note.id), "title": note.title}


@router.get("/notes/{note_id}")
async def get_note(note_id: str, db: AsyncSession = Depends(get_db)):
    note = await notes_service.get(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"id": str(note.id), "title": note.title, "content": note.content,
            "entity_type": note.entity_type, "entity_id": note.entity_id}


@router.patch("/notes/{note_id}")
async def update_note(note_id: str, payload: NoteUpdate, db: AsyncSession = Depends(get_db)):
    note = await notes_service.update(db, note_id, payload.title, payload.content)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"id": str(note.id), "title": note.title}


@router.get("/notes/entity/{entity_type}/{entity_id}")
async def get_notes_by_entity(entity_type: str, entity_id: str, db: AsyncSession = Depends(get_db)):
    notes = await notes_service.get_by_entity(db, entity_type, entity_id)
    return {"notes": [{"id": str(n.id), "title": n.title} for n in notes]}


@router.get("/notes/search")
async def search_notes(query: str, db: AsyncSession = Depends(get_db), limit: int = 20):
    notes = await notes_service.search(db, query, limit=limit)
    return {"query": query, "results": [{"id": str(n.id), "title": n.title, "snippet": n.content[:200]} for n in notes]}


# ─── Costs & Audit ─────────────────────────────────────

@router.get("/costs/summary")
async def get_costs_summary(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func, select as sa_select
    from app.models.audit import CostLog

    result = await db.execute(
        sa_select(
            func.coalesce(func.sum(CostLog.tokens_in + CostLog.tokens_out), 0),
            func.coalesce(func.sum(CostLog.cost_cents), 0),
        )
    )
    total_tokens, total_cost = result.one()

    provider_result = await db.execute(
        sa_select(CostLog.provider, func.sum(CostLog.cost_cents))
        .group_by(CostLog.provider)
    )

    return {
        "total_tokens": int(total_tokens),
        "total_cost_cents": float(total_cost),
        "by_provider": [{"provider": p, "cost_cents": float(c)} for p, c in provider_result.all()],
    }


@router.get("/costs/log")
async def get_costs_log(db: AsyncSession = Depends(get_db), limit: int = 20):
    from app.models.audit import CostLog
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(CostLog).order_by(CostLog.date.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [{"provider": l.provider, "model": l.model, "call_type": l.call_type,
             "tokens_in": l.tokens_in, "tokens_out": l.tokens_out,
             "cost_cents": float(l.cost_cents), "date": str(l.date)} for l in logs]


@router.get("/audit")
async def get_audit_log(db: AsyncSession = Depends(get_db), limit: int = 50):
    from app.models.audit import AuditLog
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(AuditLog).order_by(AuditLog.completed_at.desc().nulls_last()).limit(limit)
    )
    logs = result.scalars().all()
    return [{"action": l.action, "entity_type": l.entity_type, "entity_id": l.entity_id,
             "summary": l.summary, "status": l.status,
             "completed_at": str(l.completed_at) if l.completed_at else None} for l in logs]


# ─── User list ─────────────────────────────────────────

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    from app.models.user import User
    from sqlalchemy import select as sa_select

    result = await db.execute(sa_select(User).where(User.is_active == True))
    users = result.scalars().all()
    return [{"id": str(u.id), "email": u.email, "name": u.name, "github_username": u.github_username} for u in users]
