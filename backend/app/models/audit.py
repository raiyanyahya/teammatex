from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_log"

    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)
    llm_calls: Mapped[int | None] = mapped_column(Integer)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    # Fractional cents: real per-call costs for cheap models are sub-cent and
    # must not truncate to zero.
    estimated_cost_cents: Mapped[float | None] = mapped_column(Numeric(14, 6))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(20))


class Feedback(Base, UUIDMixin):
    __tablename__ = "feedback"

    pr_id: Mapped[str | None] = mapped_column(ForeignKey("prs.id"))
    rating: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CostLog(Base, UUIDMixin):
    __tablename__ = "cost_log"

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    call_type: Mapped[str] = mapped_column(String(50))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    # Fractional cents (see AuditLog.estimated_cost_cents).
    cost_cents: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
