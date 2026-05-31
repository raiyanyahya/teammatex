from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class Upload(UUIDMixin, Base):
    """A file a developer uploaded. The bytes live on disk under a generated
    UUID path (so a malicious original filename can't traverse); this row is the
    metadata. Scoped to ``owner_id`` (the uploader's JWT sub) — uploads are
    private per user."""

    __tablename__ = "uploads"

    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    stored_path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
