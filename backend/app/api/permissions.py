from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.permission import Permission

router = APIRouter(prefix="/permissions", tags=["permissions"])

# Canonical capabilities, their label, and the state the agent assumes when a
# capability has never been explicitly set. read_code/write_code/create_pr gate
# tools (see runtime.TOOL_CAPABILITY); merge_pr and autonomous are surfaced for
# completeness but have no tool gate yet.
CAPABILITIES: list[tuple[str, str, bool]] = [
    ("read_code", "Read code", True),
    ("write_code", "Write code", True),
    ("create_pr", "Create PRs", True),
    ("merge_pr", "Merge PRs", False),
    ("autonomous", "Autonomous mode", True),
]
_DEFAULTS = {cap: default for cap, _, default in CAPABILITIES}
_LABELS = {cap: label for cap, label, _ in CAPABILITIES}


class PermissionSet(BaseModel):
    enabled: bool


@router.get("")
async def list_permissions(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Permission))).scalars().all()
    stored = {r.capability: r.enabled for r in rows}
    return {"permissions": [
        {"capability": cap, "label": _LABELS[cap], "enabled": stored.get(cap, default)}
        for cap, default in _DEFAULTS.items()
    ]}


@router.put("/{capability}")
async def set_permission(
    capability: str, payload: PermissionSet, db: AsyncSession = Depends(get_db),
):
    if capability not in _DEFAULTS:
        raise HTTPException(status_code=404, detail=f"Unknown capability: {capability}")

    row = (await db.execute(
        select(Permission).where(Permission.capability == capability)
    )).scalar_one_or_none()
    if row:
        row.enabled = payload.enabled
    else:
        db.add(Permission(capability=capability, enabled=payload.enabled, description=_LABELS[capability]))
    await db.commit()
    return {"capability": capability, "enabled": payload.enabled}
