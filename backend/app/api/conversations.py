"""Read/manage a user's saved chat conversations.

Writes happen in the chat stream (app.api.agent); this router lists, loads, and
deletes. Everything is scoped to the caller's JWT ``sub``.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.db.session import get_db
from app.services.agent.conversations_service import (
    delete_conversation,
    get_conversation,
    list_conversations,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _owner(user: dict) -> str:
    return str(user.get("sub") or "anonymous")


@router.get("")
async def list_(user: dict = Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await list_conversations(db, _owner(user))


@router.get("/{conversation_id}")
async def get_(
    conversation_id: str,
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    convo = await get_conversation(db, _owner(user), conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="Not found")
    return convo


@router.delete("/{conversation_id}", status_code=204)
async def delete_(
    conversation_id: str,
    user: dict = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if not await delete_conversation(db, _owner(user), conversation_id):
        raise HTTPException(status_code=404, detail="Not found")
    await db.commit()
