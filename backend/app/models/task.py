from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, utcnow

# Task and PR are defined together in this module on purpose. They reference each
# other's type in their relationships (Task.prs -> list[PR], PR.task -> Task), and
# with the classes in separate modules that mutual reference forces a module-level
# import cycle (each file importing the other under TYPE_CHECKING). Co-locating
# them lets mypy resolve both forward references within one namespace, so no
# cross-module import — and no cycle — is needed. ``app.models.pr`` re-exports PR
# so existing ``from app.models.pr import PR`` call sites keep working.


class Task(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="open")
    priority: Mapped[str | None] = mapped_column(String(20))
    assigned_to: Mapped[str | None] = mapped_column(String(255))

    prs: Mapped[list["PR"]] = relationship(back_populates="task", cascade="all, delete-orphan")


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
