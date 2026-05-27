from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from structlog import get_logger

from app.db.session import get_db
from app.models.repo import Repo
from app.services.onboarding.pipeline import start_onboarding

logger = get_logger(__name__)
router = APIRouter(prefix="/repos", tags=["repos"])


class RepoCreate(BaseModel):
    github_url: str
    local_name: str | None = None


class RepoResponse(BaseModel):
    id: str
    github_url: str
    local_name: str
    default_branch: str
    is_active: bool


class BulkRepoCreate(BaseModel):
    github_urls: list[str]


def _local_name_from_url(github_url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(github_url).path.strip("/")
    return path.split("/")[-1].replace(".git", "") if "/" in path else github_url.replace(".git", "")


@router.get("", response_model=list[RepoResponse])
async def list_repos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repo).where(Repo.is_active == True))
    repos = result.scalars().all()
    return [
        RepoResponse(
            id=r.id,
            github_url=r.github_url,
            local_name=r.local_name,
            default_branch=r.default_branch,
            is_active=r.is_active,
        )
        for r in repos
    ]


@router.post("", response_model=dict, status_code=201)
async def add_repo(payload: RepoCreate, db: AsyncSession = Depends(get_db)):
    local_name = payload.local_name
    if not local_name:
        from urllib.parse import urlparse
        path = urlparse(payload.github_url).path.strip("/")
        local_name = path.split("/")[-1].replace(".git", "") if "/" in path else ""

    # If it's an org/user (no repo path), pull all repos via GitHub API
    parts = payload.github_url.rstrip("/").replace("https://github.com/", "").replace("http://github.com/", "").split("/")
    if len(parts) == 1:
        org = parts[0]
        token = await _get_github_token(db)
        if not token:
            raise HTTPException(status_code=400, detail=f"'{org}' looks like an organization. A GitHub token is required to import org repos. Save your token in Settings.")

        import httpx
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=30,
        ) as client:
            for endpoint in [f"/orgs/{org}/repos", f"/users/{org}/repos"]:
                resp = await client.get(endpoint, params={"per_page": 100, "type": "all"})
                if resp.status_code == 200:
                    break
                if resp.status_code == 401:
                    raise HTTPException(status_code=401, detail="GitHub token is invalid or expired. Update it in Settings → Integrations.")
            else:
                status = resp.status_code
                msg = resp.json().get("message", "Unknown error")
                raise HTTPException(status_code=400, detail=f"GitHub API returned {status}: {msg}")
            gh_repos = resp.json()

        added = []
        for r in gh_repos:
            url = r["clone_url"]; name = r["name"]
            existing_check = await db.execute(select(Repo).where(Repo.github_url == url))
            if existing_check.scalar_one_or_none(): continue
            repo = Repo(github_url=url, local_name=name)
            db.add(repo); await db.flush()
            added.append({"repo_id": str(repo.id), "url": url, "name": name})
        await db.commit()

        # Enqueue onboarding only after the rows are committed — start_onboarding
        # uses apply_async, so the Celery worker must be able to find each repo
        # (same race fixed in /repos/bulk).
        for item in added:
            start_onboarding(item["repo_id"], item["url"], item["name"])
        return {"org": org, "repos_added": len(added), "repos": [a["name"] for a in added]}

    existing = await db.execute(
        select(Repo).where(Repo.github_url == payload.github_url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Repository already registered")

    repo = Repo(github_url=payload.github_url, local_name=local_name)
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    pipeline_id = start_onboarding(str(repo.id), payload.github_url, local_name)

    return {
        "repo_id": str(repo.id),
        "local_name": local_name,
        "pipeline_id": pipeline_id,
        "status": "onboarding_started",
    }


@router.post("/bulk", response_model=dict, status_code=201)
async def add_repos_bulk(payload: BulkRepoCreate, db: AsyncSession = Depends(get_db)):
    """Onboard a selected set of repos in one call. Each url that isn't already
    registered is created and starts the pipeline; duplicates are skipped."""
    added: list[dict] = []
    skipped: list[str] = []

    for github_url in payload.github_urls:
        url = github_url.strip()
        if not url:
            continue

        existing = await db.execute(select(Repo).where(Repo.github_url == url))
        if existing.scalar_one_or_none():
            skipped.append(url)
            continue

        local_name = _local_name_from_url(url)
        repo = Repo(github_url=url, local_name=local_name)
        db.add(repo)
        await db.flush()
        added.append({"url": url, "repo_id": str(repo.id), "local_name": local_name})

    await db.commit()

    # Enqueue the pipeline only after the rows are committed, so the Celery
    # worker can actually find each repo (start_onboarding uses apply_async).
    for item in added:
        start_onboarding(item["repo_id"], item["url"], item["local_name"])

    return {"added": added, "skipped": skipped}


@router.delete("/{repo_id}")
async def delete_repo(repo_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a repo from TeammateX: its DB rows (PRs, onboarding state, tech-debt,
    dependency snapshots) and, best-effort, its knowledge-graph subgraph. The cloned
    checkout and vector embeddings are left for a separate cleanup pass."""
    from sqlalchemy import delete as sa_delete
    from app.models.pr import PR
    from app.models.repo import RepoOnboardingState
    from app.models.tech_debt import TechDebtItem
    from app.models.dependency import DependencySnapshot

    result = await db.execute(select(Repo).where(Repo.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    for model in (PR, RepoOnboardingState, TechDebtItem, DependencySnapshot):
        await db.execute(sa_delete(model).where(model.repo_id == repo_id))
    await db.delete(repo)
    await db.commit()

    try:
        from app.services.knowledge.graph import KnowledgeGraph
        await KnowledgeGraph().run("MATCH (n {repo_id: $id}) DETACH DELETE n", id=repo_id)
    except Exception as e:
        logger.warning("repo_delete_graph_cleanup_failed", repo_id=repo_id, error=str(e)[:120])

    return {"deleted": True, "repo_id": repo_id}


@router.post("/{repo_id}/retry")
async def retry_onboarding(repo_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.repo import Repo, RepoOnboardingState
    from app.services.onboarding.pipeline import start_onboarding

    result = await db.execute(select(Repo).where(Repo.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    await db.execute(
        select(RepoOnboardingState).where(RepoOnboardingState.repo_id == repo_id)
    )
    states = (await db.execute(
        select(RepoOnboardingState).where(RepoOnboardingState.repo_id == repo_id)
    )).scalars().all()
    for s in states:
        await db.delete(s)
    await db.commit()

    pipeline_id = start_onboarding(str(repo.id), repo.github_url, repo.local_name)
    return {"repo_id": str(repo.id), "pipeline_id": pipeline_id, "status": "retrying"}


@router.get("/{repo_id}/onboarding")
async def get_onboarding_status(repo_id: str, db: AsyncSession = Depends(get_db)):
    from uuid import UUID
    from app.models.repo import RepoOnboardingState

    # A malformed (non-UUID) id has no onboarding state; report empty rather
    # than letting the typed column query raise a 500 on the bad cast.
    try:
        UUID(repo_id)
    except ValueError:
        return {"repo_id": repo_id, "stages": []}

    result = await db.execute(
        select(RepoOnboardingState)
        .where(RepoOnboardingState.repo_id == repo_id)
        .order_by(RepoOnboardingState.stage)
    )
    states = result.scalars().all()
    return {
        "repo_id": repo_id,
        "stages": [
            {
            "stage": s.stage,
            "status": s.status,
            "progress": s.progress,
            "error": s.error,
            "completed_at": str(s.completed_at) if s.completed_at else None,
        }
        for s in states
    ],
}


async def _get_github_token(db: AsyncSession) -> str:
    from app.models.app_config import AppConfig
    result = await db.execute(select(AppConfig).where(AppConfig.key == "github_token"))
    row = result.scalar_one_or_none()
    if row and row.value:
        return row.value.get("token", "")
    return ""
