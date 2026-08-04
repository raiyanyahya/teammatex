from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class BlockedTask(Base, UUIDMixin):
    __tablename__ = "blocked_tasks"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    answer: Mapped[str | None] = mapped_column(Text)
