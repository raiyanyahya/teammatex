from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class TrustLevel(Base, UUIDMixin):
    __tablename__ = "trust_level"

    level: Mapped[int] = mapped_column(Integer, default=0)
    level_name: Mapped[str] = mapped_column(String(50))
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    promoted_by: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (CheckConstraint("level BETWEEN 0 AND 4", name="ck_trust_level_range"),)


class TrustMetrics(Base, UUIDMixin):
    __tablename__ = "trust_metrics"

    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    pr_merge_rate: Mapped[float] = mapped_column(Float, default=0.0)
    pr_iteration_avg: Mapped[float] = mapped_column(Float, default=0.0)
    feedback_score: Mapped[float] = mapped_column(Float, default=0.0)
    question_quality: Mapped[float] = mapped_column(Float, default=0.0)
    test_pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    task_completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
