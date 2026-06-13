from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.db.session import get_db
from app.config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/digest")
async def get_weekly_digest():
    import asyncio
    from app.services.reporting.digest import digest_generator
    # generate_weekly opens a sync engine and runs blocking queries — keep it
    # off the event loop.
    digest = await asyncio.to_thread(digest_generator.generate_weekly, settings.database_url)
    return digest


@router.get("/digest/markdown")
async def get_weekly_digest_md():
    import asyncio
    from app.services.reporting.digest import digest_generator
    digest = await asyncio.to_thread(digest_generator.generate_weekly, settings.database_url)
    return {"markdown": digest_generator.format_markdown(digest)}


@router.post("/digest/send")
async def send_digest_now():
    """Generate the weekly digest and deliver it to Slack now (same job the beat
    schedule runs Mondays). Returns delivery status; no-ops if Slack isn't set up."""
    import asyncio
    from app.workers.tasks import send_weekly_digest
    return await asyncio.to_thread(send_weekly_digest)


@router.get("/docs/{repo_id}")
async def get_repo_docs(repo_id: str):
    from app.services.reporting.docs_generator import docs_generator
    from sqlalchemy import create_engine, select, text as sqla_text
    from sqlalchemy.orm import Session
    from app.models.repo import Repo

    engine = create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"))
    try:
        with Session(engine) as db:
            repo = db.execute(select(Repo).where(Repo.id == repo_id)).scalar_one_or_none()
            if not repo:
                raise HTTPException(status_code=404, detail="Repo not found")
            result = await docs_generator.generate_repo_docs(repo_id, repo.local_name)
            return result
    finally:
        engine.dispose()


@router.get("/docs/entity/{entity_name}")
async def get_entity_docs(entity_name: str, repo_id: str = Query("")):
    from app.services.reporting.docs_generator import docs_generator
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.models.repo import Repo

    if not repo_id:
        engine = create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"))
        try:
            with Session(engine) as db:
                repo = db.execute(select(Repo).where(Repo.is_active == True)).scalars().first()
                if repo:
                    repo_id = str(repo.id)
        finally:
            engine.dispose()

    if not repo_id:
        raise HTTPException(status_code=404, detail="No active repos")

    content = await docs_generator.generate_entity_docs(repo_id, entity_name)
    return {"entity": entity_name, "content": content}


@router.get("/sync/status")
async def get_sync_status():
    from app.services.agent.auto_sync import auto_sync
    last_polls = {}
    for repo_name, dt in auto_sync._last_poll.items():
        last_polls[repo_name] = dt.isoformat() if dt else None
    return {
        "polling": auto_sync._running,
        "webhook_enabled": settings.auto_sync_webhook_enabled,
        "poll_interval_minutes": settings.auto_sync_poll_interval_minutes,
        "last_poll": last_polls,
    }


@router.post("/sync/trigger")
async def trigger_manual_sync():
    from app.services.agent.auto_sync import auto_sync
    await auto_sync._poll_all_repos()
    return {"status": "sync_complete"}


@router.post("/pr/review")
async def review_pr(repo_id: str, pr_title: str, pr_body: str = "",
                    changed_files: list[str] | None = None, diff: str = ""):
    from app.services.agent.pr_reviewer import pr_reviewer
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.models.repo import Repo

    engine = create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"))
    try:
        with Session(engine) as db:
            repo = db.execute(select(Repo).where(Repo.id == repo_id)).scalar_one_or_none()
            if not repo:
                raise HTTPException(status_code=404, detail="Repo not found")
            result = await pr_reviewer.review(repo_id, repo.local_name, pr_title, pr_body,
                                               changed_files or [], diff)
            return result
    finally:
        engine.dispose()


@router.get("/blame/trace")
async def blame_trace(entity_name: str, repo_id: str, file_path: str = ""):
    from app.services.agent.blame_tracer import blame_tracer
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.models.repo import Repo

    engine = create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"))
    try:
        with Session(engine) as db:
            repo = db.execute(select(Repo).where(Repo.id == repo_id)).scalar_one_or_none()
            if not repo:
                raise HTTPException(status_code=404, detail="Repo not found")
            result = await blame_tracer.trace(repo_id, repo.local_name, entity_name, file_path,
                                               f"/data/repos/{repo.local_name}")
            return result
    finally:
        engine.dispose()
