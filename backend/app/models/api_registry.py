from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow

# The initial migration created these as Postgres text arrays (VARCHAR[]). The
# model had drifted to JSON, so every INSERT hit "column is of type
# character varying[] but expression is of type json" and POST /api-registry
# 500'd in a real (migration-built) deployment — invisible to the tests, which
# build the schema straight from this model. Match the deployed column type
# (ARRAY on Postgres) and keep JSON on SQLite so the model still builds there.
_StrList = postgresql.ARRAY(String()).with_variant(JSON(), "sqlite")


class APIRegistryEntry(Base, UUIDMixin):
    __tablename__ = "api_registry"

    domain: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    allowed_methods: Mapped[list | None] = mapped_column(_StrList)
    allowed_paths: Mapped[list | None] = mapped_column(_StrList)
    rate_limit_per_hour: Mapped[int | None] = mapped_column(Integer)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
