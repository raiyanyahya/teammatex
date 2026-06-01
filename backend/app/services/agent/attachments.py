"""Inline an uploaded file's text into a chat message as context.

The agent already knows the codebase; attaching gives it the *other half* — a
stack trace, a log, a design doc. We decode the upload as UTF-8 and prepend it to
the user's message. A foreign/missing/malformed id is ignored (message sent
as-is) so a bad attachment never fails the whole chat; binary or oversized files
get a short note instead of garbled bytes.
"""
from __future__ import annotations

import uuid as _uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upload import Upload

ATTACH_MAX_BYTES = 50 * 1024  # cap injected text so a big file can't blow the context


async def build_attached_message(
    db: AsyncSession, upload_id: str | None, owner: str, message: str
) -> str:
    if not upload_id:
        return message
    try:
        _uuid.UUID(upload_id)
    except ValueError:
        return message

    up = (await db.execute(
        select(Upload).where(Upload.id == upload_id, Upload.owner_id == owner)
    )).scalar_one_or_none()
    if up is None:
        return message

    try:
        data = Path(up.stored_path).read_bytes()
    except OSError:
        return f'(Attached file "{up.filename}" could not be read.)\n\n{message}'

    truncated = len(data) > ATTACH_MAX_BYTES
    try:
        text = data[:ATTACH_MAX_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return f'(Attached file "{up.filename}" is binary and can\'t be read as text.)\n\n{message}'

    note = "\n…(truncated)" if truncated else ""
    return f'Attached file "{up.filename}":\n{text}{note}\n\n---\n\n{message}'
