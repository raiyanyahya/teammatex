from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.api_registry import APIRegistryEntry

logger = get_logger(__name__)

router = APIRouter(prefix="/api-registry", tags=["api_registry"])


class RegistryEntryCreate(BaseModel):
    domain: str
    description: str | None = None
    allowed_methods: list[str] = ["GET"]
    allowed_paths: list[str] = ["/*"]
    rate_limit_per_hour: int | None = 100
    requires_approval: bool = False


class RegistryEntryUpdate(BaseModel):
    description: str | None = None
    allowed_methods: list[str] | None = None
    allowed_paths: list[str] | None = None
    rate_limit_per_hour: int | None = None
    requires_approval: bool | None = None
    status: str | None = None


class CheckURLRequest(BaseModel):
    url: str
    method: str = "GET"


@router.get("")
async def list_registry(
    db: AsyncSession = Depends(get_db),
    status: str = "active",
):
    result = await db.execute(
        select(APIRegistryEntry).where(APIRegistryEntry.status == status)
    )
    entries = result.scalars().all()
    return {
        "entries": [
            {
                "id": str(e.id),
                "domain": e.domain,
                "description": e.description,
                "allowed_methods": e.allowed_methods,
                "rate_limit_per_hour": e.rate_limit_per_hour,
                "requires_approval": e.requires_approval,
                "status": e.status,
            }
            for e in entries
        ]
    }


# add/patch/delete change the approved-egress allowlist that gates the agent's
# http_request tool, so they are admin-only. Reads, the /check probe, and the
# agent's own /suggest (which only creates a *pending* entry needing approval)
# stay open to any authenticated user.
@router.post("", status_code=201)
async def add_entry(
    payload: RegistryEntryCreate,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(APIRegistryEntry).where(APIRegistryEntry.domain == payload.domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Domain already registered")

    entry = APIRegistryEntry(
        domain=payload.domain,
        description=payload.description,
        allowed_methods=payload.allowed_methods,
        allowed_paths=payload.allowed_paths,
        rate_limit_per_hour=payload.rate_limit_per_hour,
        requires_approval=payload.requires_approval,
        added_by="teammate",
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    return {"id": str(entry.id), "domain": entry.domain, "status": "active"}


@router.patch("/{entry_id}")
async def update_entry(
    entry_id: str, payload: RegistryEntryUpdate,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIRegistryEntry).where(APIRegistryEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if payload.description is not None:
        entry.description = payload.description
    if payload.allowed_methods is not None:
        entry.allowed_methods = payload.allowed_methods
    if payload.allowed_paths is not None:
        entry.allowed_paths = payload.allowed_paths
    if payload.rate_limit_per_hour is not None:
        entry.rate_limit_per_hour = payload.rate_limit_per_hour
    if payload.requires_approval is not None:
        entry.requires_approval = payload.requires_approval
    if payload.status is not None:
        entry.status = payload.status

    await db.commit()
    return {"id": str(entry.id), "status": entry.status}


@router.delete("/{entry_id}")
async def remove_entry(
    entry_id: str,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIRegistryEntry).where(APIRegistryEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(entry)
    await db.commit()
    return {"id": entry_id, "status": "removed"}


@router.post("/check")
async def check_url(payload: CheckURLRequest, db: AsyncSession = Depends(get_db)):
    domain = urlparse(payload.url).netloc or urlparse(payload.url).hostname or ""
    if not domain:
        return {"allowed": False, "reason": "Could not parse domain from URL"}

    result = await db.execute(
        select(APIRegistryEntry).where(
            APIRegistryEntry.domain == domain,
            APIRegistryEntry.status == "active",
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        return {
            "allowed": False,
            "domain": domain,
            "reason": "Domain not in approved registry",
            "can_suggest": True,
        }

    if entry.allowed_methods and payload.method.upper() not in entry.allowed_methods:
        return {
            "allowed": False,
            "domain": domain,
            "reason": f"Method {payload.method} not allowed (allowed: {entry.allowed_methods})",
        }

    path = urlparse(payload.url).path or "/"
    path_allowed = False
    if entry.allowed_paths:
        from fnmatch import fnmatch
        path_allowed = any(fnmatch(path, p) for p in entry.allowed_paths)
    else:
        path_allowed = True

    if not path_allowed:
        return {
            "allowed": False,
            "domain": domain,
            "reason": f"Path {path} not in allowed paths",
        }

    return {
        "allowed": True,
        "domain": domain,
        "rate_limit_per_hour": entry.rate_limit_per_hour,
        "requires_approval": entry.requires_approval,
    }


@router.post("/suggest")
async def suggest_domain(payload: RegistryEntryCreate, db: AsyncSession = Depends(get_db)):
    """Suggested by the teammate for team approval."""
    existing = await db.execute(
        select(APIRegistryEntry).where(APIRegistryEntry.domain == payload.domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already registered or suggested")

    entry = APIRegistryEntry(
        domain=payload.domain,
        description=payload.description,
        allowed_methods=payload.allowed_methods,
        allowed_paths=payload.allowed_paths,
        rate_limit_per_hour=payload.rate_limit_per_hour,
        requires_approval=True,
        added_by="teammate",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    logger.info("api_registry_suggestion", domain=payload.domain, description=payload.description)
    return {"id": str(entry.id), "domain": entry.domain, "status": "pending_approval"}
