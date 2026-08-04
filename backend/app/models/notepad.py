from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Notepad(Base):
    """One always-saved scratchpad per developer. ``owner_id`` (the JWT sub) is
    the primary key, so there is exactly one row per user, upserted on save."""

    __tablename__ = "notepad"

    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow, default=utcnow
    )
