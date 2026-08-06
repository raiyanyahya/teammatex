from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from app.services.agent.confidence import (
    ConfidenceTier,
    compute_confidence,
    flag_if_low,
    is_low_confidence,
)

logger = structlog.get_logger(__name__)


@dataclass
class MemoryItem:
    key: str
    value: str
    category: str  # "conversation", "preference", "feedback", "task_context"
    importance: float = 0.5
    initial_confidence: float = 0.8
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    evidence_count: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0

    @property
    def confidence(self) -> float:
        score, _ = compute_confidence(
            self.initial_confidence,
            verified_at=self.verified_at,
            category=self._decay_category(),
            evidence_count=self.evidence_count,
        )
        return score

    @property
    def confidence_tier(self) -> ConfidenceTier:
        _, tier = compute_confidence(
            self.initial_confidence,
            verified_at=self.verified_at,
            category=self._decay_category(),
            evidence_count=self.evidence_count,
        )
        return tier

    @property
    def is_low_confidence(self) -> bool:
        return is_low_confidence(self.confidence)

    def _decay_category(self) -> str:
        if self.category == "conversation":
            return "default"
        if self.category == "feedback":
            return "feedback"
        if self.category == "task_context":
            return "decision"
        if self.category == "preference":
            return "convention"
        return "default"


class MemoryManager:
    MAX_WORKING_MEMORY = 20
    MAX_EPISODIC_MEMORY = 200
    TOKEN_BUDGET = 8000

    def __init__(self):
        self.working: list[MemoryItem] = []
        self.episodic: list[MemoryItem] = []
        self.preferences: dict[str, str] = {}
        self.learned_conventions: list[str] = []

    def remember(
        self,
        key: str,
        value: str,
        category: str,
        importance: float = 0.5,
        initial_confidence: float | None = None,
    ):
        if initial_confidence is None:
            initial_confidence = 0.6 + importance * 0.3
        item = MemoryItem(
            key=key,
            value=value,
            category=category,
            importance=importance,
            initial_confidence=initial_confidence,
        )
        if importance >= 0.7:
            self.working.insert(0, item)
        else:
            self.working.append(item)

        if len(self.working) > self.MAX_WORKING_MEMORY:
            evicted = self.working.pop()
            self.episodic.append(evicted)

        if len(self.episodic) > self.MAX_EPISODIC_MEMORY:
            self.episodic.sort(
                key=lambda m: (m.importance + m.confidence * 0.5, m.last_accessed),
                reverse=True,
            )
            self.episodic = self.episodic[: self.MAX_EPISODIC_MEMORY]

    def recall(self, key: str) -> MemoryItem | None:
        for item in self.working:
            if item.key == key:
                item.last_accessed = datetime.now(UTC)
                item.access_count += 1
                return item
        for item in self.episodic:
            if item.key == key:
                item.last_accessed = datetime.now(UTC)
                item.access_count += 1
                self.working.insert(0, item)
                if len(self.working) > self.MAX_WORKING_MEMORY:
                    self.working.pop()
                return item
        return None

    def recall_recent(
        self, category: str | None = None, limit: int = 10, min_confidence: float = 0.0
    ) -> list[MemoryItem]:
        datetime.now(UTC)
        items = self.working + self.episodic
        if category:
            items = [i for i in items if i.category == category]
        items = [i for i in items if i.confidence >= min_confidence]
        items.sort(key=lambda m: (m.confidence + m.importance * 0.5, m.last_accessed), reverse=True)
        return items[:limit]

    MAX_PREFERENCES = 100
    MAX_CONVENTIONS = 50

    def learn_preference(self, key: str, value: str):
        if len(self.preferences) >= self.MAX_PREFERENCES:
            oldest = next(iter(self.preferences))
            del self.preferences[oldest]
        self.preferences[key] = value
        logger.info("preference_learned", key=key, value=value[:100])

    def get_preference(self, key: str) -> str | None:
        return self.preferences.get(key)

    def learn_convention(self, convention: str):
        if convention not in self.learned_conventions:
            if len(self.learned_conventions) >= self.MAX_CONVENTIONS:
                self.learned_conventions.pop(0)
            self.learned_conventions.append(convention)
            logger.info("convention_learned", convention=convention[:100])

    def get_conventions(self) -> str:
        if not self.learned_conventions:
            return "(No team conventions learned yet.)"
        return "\n".join(f"- {c}" for c in self.learned_conventions)

    def build_context_prompt(self) -> str:
        parts: list[str] = []

        recent = self.recall_recent(category="task_context", limit=5)
        if recent:
            parts.append("## Recent Task Context")
            for item in recent:
                flag = flag_if_low(item.confidence, item.key)
                parts.append(f"- {item.key}: {item.value[:200]}{' ' + flag if flag else ''}")

        feedback = self.recall_recent(category="feedback", limit=3)
        if feedback:
            parts.append("\n## Recent Feedback")
            for item in feedback:
                flag = flag_if_low(item.confidence, item.key)
                parts.append(f"- {item.key}: {item.value[:200]}{' ' + flag if flag else ''}")

        convs = self.get_conventions()
        if convs:
            parts.append(f"\n## Team Conventions\n{convs}")

        prefs = self.preferences
        if prefs:
            parts.append("\n## Team Preferences")
            for k, v in prefs.items():
                parts.append(f"- {k}: {v}")

        low_conf = [i for i in (self.working + self.episodic) if i.is_low_confidence]
        if low_conf:
            parts.append("\n## ⚠️ Low-Confidence Memories (may need verification)")
            for item in low_conf[:5]:
                parts.append(
                    f"- [{item.confidence_tier.value}] {item.key}: confidence={item.confidence:.2f}"
                )

        return "\n".join(parts) if parts else ""

    async def persist_to_db(self, db):

        from sqlalchemy import select

        from app.models.app_config import AppConfig

        data = {
            "preferences": dict(self.preferences),
            "conventions": list(self.learned_conventions),
            "episodic": [
                {
                    "key": m.key,
                    "value": m.value,
                    "category": m.category,
                    "importance": m.importance,
                    "initial_confidence": m.initial_confidence,
                    "evidence_count": m.evidence_count,
                    "verified_at": m.verified_at.isoformat() if m.verified_at else None,
                }
                for m in self.episodic[:50]
            ],
        }
        result = await db.execute(select(AppConfig).where(AppConfig.key == "memory_state"))
        row = result.scalar_one_or_none()
        if row:
            row.value = data
        else:
            db.add(AppConfig(key="memory_state", value=data))
        await db.commit()

    async def load_from_db(self, db):
        from sqlalchemy import select

        from app.models.app_config import AppConfig

        result = await db.execute(select(AppConfig).where(AppConfig.key == "memory_state"))
        row = result.scalar_one_or_none()
        if row and row.value:
            data = row.value
            self.preferences = data.get("preferences", {})
            self.learned_conventions = data.get("conventions", [])
            for item in data.get("episodic", []):
                verified_at = (
                    datetime.fromisoformat(item["verified_at"])
                    if item.get("verified_at")
                    else datetime.now(UTC)
                )
                mem = MemoryItem(
                    key=item["key"],
                    value=item["value"],
                    category=item["category"],
                    importance=item.get("importance", 0.5),
                    initial_confidence=item.get("initial_confidence", 0.8),
                    evidence_count=item.get("evidence_count", 1),
                    verified_at=verified_at,
                )
                self.episodic.append(mem)


# Module-level singleton, mirroring auto_sync/pr_reviewer/blame_tracer/etc.
# auto_sync._notify_changes imports this; without it that path raised ImportError.
memory_manager = MemoryManager()
