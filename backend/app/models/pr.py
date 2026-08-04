from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, utcnow

if TYPE_CHECKING:
    from app.models.task import Task


class PR(Base, UUIDMixin):
    __tablename__ = "prs"

    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id"), index=True)
    github_pr_number: Mapped[int | None] = mapped_column(Integer)
    branch: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped["Task | None"] = relationship(back_populates="prs")
