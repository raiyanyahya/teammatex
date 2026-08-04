from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, utcnow


class Repo(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "repos"

    github_url: Mapped[str] = mapped_column(String(1024))
    local_name: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    language_stats: Mapped[dict | None] = mapped_column(JSON)
    clone_path: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    onboarding_states: Mapped[list["RepoOnboardingState"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class RepoOnboardingState(Base, UUIDMixin):
    __tablename__ = "repo_onboarding_state"

    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id"), index=True)
    stage: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    repo: Mapped["Repo"] = relationship(back_populates="onboarding_states")
