"""Per-user always-saved scratchpad. One row per user, upserted on save."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.db.session import get_db
from app.models.notepad import Notepad

router = APIRouter(prefix="/notepad", tags=["notepad"])


class NotepadBody(BaseModel):
    content: str = ""


def _owner(user: dict) -> str:
    return str(user.get("sub") or "anonymous")


@router.get("")
async def get_notepad(user: dict = Depends(require_user), db: AsyncSession = Depends(get_db)):
    note = (await db.execute(
        select(Notepad).where(Notepad.owner_id == _owner(user))
    )).scalar_one_or_none()
    return {
        "content": note.content if note else "",
        "updated_at": str(note.updated_at) if note else None,
    }


@router.post("")
async def save_notepad(
    body: NotepadBody,
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    owner = _owner(user)
    note = (await db.execute(
        select(Notepad).where(Notepad.owner_id == owner)
    )).scalar_one_or_none()
    if note is None:
        note = Notepad(owner_id=owner, content=body.content)
        db.add(note)
    else:
        note.content = body.content
        note.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(note)
    return {"content": note.content, "updated_at": str(note.updated_at)}
