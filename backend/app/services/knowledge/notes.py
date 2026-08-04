from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.models.note import Note

logger = get_logger(__name__)


class NotesService:
    async def create(
        self,
        db: AsyncSession,
        title: str,
        content: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> Note:
        note = Note(
            title=title,
            content=content,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(note)
        await db.commit()
        await db.refresh(note)
        return note

    async def list_notes(self, db: AsyncSession, limit: int = 50) -> list[Note]:
        result = await db.execute(select(Note).order_by(Note.updated_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_by_entity(self, db: AsyncSession, entity_type: str, entity_id: str) -> list[Note]:
        result = await db.execute(
            select(Note)
            .where(Note.entity_type == entity_type, Note.entity_id == entity_id)
            .order_by(Note.updated_at.desc())
        )
        return list(result.scalars().all())

    async def search(self, db: AsyncSession, query: str, limit: int = 20) -> list[Note]:
        result = await db.execute(
            select(Note)
            .where((Note.title.ilike(f"%{query}%")) | (Note.content.ilike(f"%{query}%")))
            .order_by(Note.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, note_id: str) -> Note | None:
        result = await db.execute(select(Note).where(Note.id == note_id))
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, note_id: str, title: str | None = None, content: str | None = None
    ) -> Note | None:
        note = await self.get(db, note_id)
        if not note:
            return None
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        await db.commit()
        await db.refresh(note)
        return note
