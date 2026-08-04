"""Persistence for chat conversations, scoped to the caller's JWT ``sub``.

Mirrors the uploads/notepad ownership model: ``owner_id`` is a free string, so
this never casts to uuid or hits a FK. Only user/assistant *text* is stored —
tool calls and sources are ephemeral and not reloaded on an old thread.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


def _title_from(message: str) -> str:
    collapsed = " ".join((message or "").split())
    return collapsed[:60] or "New conversation"


def _valid_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        _uuid.UUID(value)
        return True
    except ValueError:
        return False


async def _owned(db: AsyncSession, owner: str, conversation_id: str | None) -> Conversation | None:
    if not _valid_uuid(conversation_id):
        return None
    return (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.owner_id == owner
            )
        )
    ).scalar_one_or_none()


async def get_or_create(
    db: AsyncSession, owner: str, conversation_id: str | None, first_message: str
) -> Conversation:
    """Return the owner's existing conversation, or create a new one titled from
    the first message. A missing/foreign/malformed id starts a fresh thread."""
    existing = await _owned(db, owner, conversation_id)
    if existing is not None:
        return existing
    convo = Conversation(owner_id=owner, title=_title_from(first_message))
    db.add(convo)
    await db.flush()  # assign the id without ending the request transaction
    return convo


async def save_message(db: AsyncSession, conversation_id: str, role: str, content: str) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    return msg


async def list_conversations(db: AsyncSession, owner: str, q: str | None = None) -> list[dict]:
    """List the owner's conversations, newest first. With `q`, return only those
    whose title or any message content matches (case-insensitive substring)."""
    stmt = select(Conversation).where(Conversation.owner_id == owner)
    if q and q.strip():
        like = f"%{q.strip()}%"
        matching_convo_ids = select(Message.conversation_id).where(Message.content.ilike(like))
        stmt = stmt.where(Conversation.title.ilike(like) | Conversation.id.in_(matching_convo_ids))
    rows = (await db.execute(stmt.order_by(Conversation.created_at.desc()))).scalars().all()
    return [
        {"id": c.id, "title": c.title, "created_at": str(c.created_at) if c.created_at else None}
        for c in rows
    ]


async def export_conversation_markdown(
    db: AsyncSession, owner: str, conversation_id: str
) -> str | None:
    """Render an owned conversation as Markdown for download, or None if not found."""
    convo = await get_conversation(db, owner, conversation_id)
    if convo is None:
        return None
    lines = [f"# {convo['title']}", ""]
    if convo.get("created_at"):
        lines += [f"_Started {convo['created_at']}_", ""]
    for m in convo["messages"]:
        who = "You" if m["role"] == "user" else "TeammateX"
        lines += [f"## {who}", "", m["content"] or "", ""]
    return "\n".join(lines)


async def get_conversation(db: AsyncSession, owner: str, conversation_id: str) -> dict | None:
    convo = await _owned(db, owner, conversation_id)
    if convo is None:
        return None
    msgs = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": convo.id,
        "title": convo.title,
        "created_at": str(convo.created_at) if convo.created_at else None,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": str(m.created_at) if m.created_at else None,
            }
            for m in msgs
        ],
    }


async def delete_conversation(db: AsyncSession, owner: str, conversation_id: str) -> bool:
    convo = await _owned(db, owner, conversation_id)
    if convo is None:
        return False
    await db.delete(convo)
    await db.flush()
    return True
