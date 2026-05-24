from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class APIRegistryEntry(Base, UUIDMixin):
    __tablename__ = "api_registry"

    domain: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    allowed_methods: Mapped[list | None] = mapped_column(JSON)
    allowed_paths: Mapped[list | None] = mapped_column(JSON)
    rate_limit_per_hour: Mapped[int | None] = mapped_column(Integer)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
