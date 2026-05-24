from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

import json

from app.db.session import get_db
from app.models.integration import Integration
from app.services.integrations.base import IntegrationRegistry
from app.utils.crypto import encrypt, decrypt

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationConfig(BaseModel):
    provider: str
    credentials: dict
    enabled: bool = True
    webhook_secret: str | None = None


class IntegrationStatus(BaseModel):
    provider: str
    enabled: bool
    connected: bool
    scm: bool
    pm: bool
    chat: bool


# ─── CRUD ────────────────────────────────────────────────

@router.get("")
async def list_integrations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Integration))
    integrations = result.scalars().all()
    return {
        "integrations": [
            {"provider": i.provider, "enabled": i.enabled, "config": i.config}
            for i in integrations
        ]
    }


@router.post("", status_code=201)
async def configure_integration(payload: IntegrationConfig, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Integration).where(Integration.provider == payload.provider)
    )
    integration = existing.scalar_one_or_none()

    if integration:
        integration.credentials_encrypted = encrypt(json.dumps(payload.credentials))
        integration.enabled = payload.enabled
        integration.webhook_secret = payload.webhook_secret
        integration.config = payload.credentials if isinstance(payload.credentials, dict) else {}
    else:
        integration = Integration(
            provider=payload.provider,
            credentials_encrypted=encrypt(json.dumps(payload.credentials)),
            enabled=payload.enabled,
            webhook_secret=payload.webhook_secret,
            config=payload.credentials if isinstance(payload.credentials, dict) else {},
        )
        db.add(integration)

    await db.commit()
    await _initialize_provider(payload.provider, payload.credentials)

    return {"provider": payload.provider, "enabled": payload.enabled, "status": "configured"}


@router.delete("/{provider}")
async def remove_integration(provider: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Integration).where(Integration.provider == provider)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.delete(integration)
    await db.commit()
    return {"provider": provider, "status": "removed"}


@router.get("/status")
async def integration_status(db: AsyncSession = Depends(get_db)):
    scm = IntegrationRegistry.get_scm()
    pm = IntegrationRegistry.get_pm()
    chat = IntegrationRegistry.get_chat()

    result = await db.execute(select(Integration))
    integrations = {i.provider: i for i in result.scalars().all()}

    return {
        "github": {"enabled": integrations.get("github", Integration()).enabled, "connected": scm is not None},
        "jira": {"enabled": integrations.get("jira", Integration()).enabled, "connected": pm is not None},
        "slack": {"enabled": integrations.get("slack", Integration()).enabled, "connected": chat is not None},
    }


# ─── Provider Actions ────────────────────────────────────

@router.get("/github/repos")
async def list_github_repos():
    """Fetch repos from GitHub using the saved token, or fall back to the env var."""
    import httpx
    from sqlalchemy import select as sa_select

    token = None
    try:
        from app.db.session import _init_engine
        _init_engine()
        from app.db.session import async_session_factory
        from app.models.integration import Integration
        async with async_session_factory() as db:
            result = await db.execute(sa_select(Integration).where(Integration.provider == "github"))
            row = result.scalar_one_or_none()
            if row and row.credentials_encrypted:
                from app.utils.crypto import decrypt
                import json
                creds = json.loads(decrypt(row.credentials_encrypted))
                token = creds.get("token")
    except Exception:
        pass

    if not token:
        scm = IntegrationRegistry.get_scm()
        if not scm:
            raise HTTPException(status_code=400, detail="No GitHub token configured")
        repos = await scm.list_repos()
    else:
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        ) as client:
            response = await client.get("/user/repos", params={"per_page": 50, "sort": "updated"})
            response.raise_for_status()
            repos = [
                {"name": r["full_name"], "url": r["clone_url"], "default_branch": r["default_branch"],
                 "private": r.get("private", False), "language": r.get("language")}
                for r in response.json()
            ]

    return {"repos": repos}


@router.get("/jira/projects")
async def list_jira_projects():
    pm = IntegrationRegistry.get_pm()
    if not pm:
        raise HTTPException(status_code=400, detail="Jira integration not configured")
    projects = await pm.list_projects()
    return {"projects": projects}


@router.get("/jira/boards/{project_key}")
async def list_jira_boards(project_key: str):
    pm = IntegrationRegistry.get_pm()
    if not pm:
        raise HTTPException(status_code=400, detail="Jira integration not configured")
    boards = await pm.list_boards(project_key)
    return {"project": project_key, "boards": [{"id": b.id, "name": b.name} for b in boards]}


@router.get("/jira/sprints/{board_id}")
async def list_jira_sprints(board_id: str):
    pm = IntegrationRegistry.get_pm()
    if not pm:
        raise HTTPException(status_code=400, detail="Jira integration not configured")
    sprints = await pm.list_sprints(board_id)
    return {"board_id": board_id, "sprints": [{"id": s.id, "name": s.name, "state": s.state} for s in sprints]}


@router.get("/jira/active-sprint/{board_id}")
async def get_active_sprint(board_id: str):
    pm = IntegrationRegistry.get_pm()
    if not pm:
        raise HTTPException(status_code=400, detail="Jira integration not configured")
    sprint = await pm.get_active_sprint(board_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="No active sprint")
    issues = await pm.get_sprint_issues(sprint.id)
    return {
        "sprint": {"id": sprint.id, "name": sprint.name, "state": sprint.state},
        "issues": [
            {"key": i.key, "title": i.title, "status": i.status, "assignee": i.assignee}
            for i in issues
        ],
    }


@router.get("/slack/channels")
async def list_slack_channels():
    chat = IntegrationRegistry.get_chat()
    if not chat:
        raise HTTPException(status_code=400, detail="Slack integration not configured")
    channels = await chat.list_channels()
    return {"channels": [{"id": c.id, "name": c.name} for c in channels]}


async def _initialize_provider(provider: str, credentials: dict) -> None:
    if provider == "github":
        from app.services.integrations.github import init_github
        init_github(credentials.get("token"))
        logger.info("github_initialized")
    elif provider == "jira":
        from app.services.integrations.jira import init_jira
        init_jira(credentials.get("url"), credentials.get("email"), credentials.get("token"))
        logger.info("jira_initialized")
    elif provider == "slack":
        from app.services.integrations.slack import init_slack
        init_slack(credentials.get("token"))
        logger.info("slack_initialized")
