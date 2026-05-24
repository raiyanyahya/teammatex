from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class TechDebtItem(Base, UUIDMixin):
    __tablename__ = "tech_debt_items"

    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    line_number: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    debt_type: Mapped[str] = mapped_column("type", String(50))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
