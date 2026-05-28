from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.knowledge.embeddings import EmbeddingService
from app.services.knowledge.graph import KnowledgeGraph
from app.services.knowledge.notes import NotesService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
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
        "total_cost_cents": int(total_cost),
        "by_provider": [{"provider": p, "cost_cents": int(c)} for p, c in provider_result.all()],
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
             "cost_cents": l.cost_cents, "date": str(l.date)} for l in logs]


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
