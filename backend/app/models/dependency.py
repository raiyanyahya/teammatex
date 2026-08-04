from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class DependencySnapshot(Base, UUIDMixin):
    __tablename__ = "dependency_snapshots"

    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id"), index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    snapshot: Mapped[dict] = mapped_column(JSON)
