from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Concept(Base, UUIDMixin, TimestampMixin):
    """LLM-extracted concept cards for the Knowledge page.

    Generated per-repo by `ConceptExtractor`. `cat` is one of `module`,
    `subsystem`, `project`, `concept` (matching the design's taxonomy):
      - module     · a top-level code area like `auth`, `billing`
      - subsystem  · a cross-cutting capability like `observability`, `CI cache`
      - project    · an in-flight migration / initiative
      - concept    · a repeating pattern or invariant (`rate-limit`, `idempotency`)

    `experts` is a JSON list of {name, email, weight} so the card can render
    `@maya, @jin` and we keep enough info to attribute changes later.
    Uniqueness is (repo_id, name) so re-running the generator upserts rather
    than duplicates.
    """

    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("repo_id", "name", name="uq_concept_repo_name"),)

    repo_id: Mapped[str | None] = mapped_column(ForeignKey("repos.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    cat: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    files: Mapped[int] = mapped_column(Integer, default=0)
    refs: Mapped[int] = mapped_column(Integer, default=0)
    experts: Mapped[list | None] = mapped_column(JSON)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generator_model: Mapped[str | None] = mapped_column(String(120))
