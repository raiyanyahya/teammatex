from datetime import datetime, timezone, timedelta
from enum import Enum
from math import log


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


CONFIDENCE_THRESHOLDS = {
    ConfidenceTier.HIGH: 0.8,
    ConfidenceTier.MEDIUM: 0.5,
    ConfidenceTier.LOW: 0.3,
}

HALF_LIFE_DAYS = {
    "convention": None,
    "decision": 180,
    "gotcha": 90,
    "relationship": 120,
    "search_result": None,
    "feedback": 60,
    "default": 90,
}


def compute_confidence(
    initial: float,
    verified_at: datetime | None = None,
    category: str = "default",
    evidence_count: int = 1,
) -> tuple[float, ConfidenceTier]:
    confidence = min(1.0, max(0.0, initial))

    if verified_at is not None:
        half_life_days = HALF_LIFE_DAYS.get(category, HALF_LIFE_DAYS["default"])
        if half_life_days is not None:
            age = datetime.now(timezone.utc) - verified_at
            half_life = timedelta(days=half_life_days)
            elapsed_half_lives = age / half_life
            confidence *= 0.5 ** elapsed_half_lives

    if evidence_count > 1:
        confidence = 1.0 - (1.0 - confidence) / evidence_count

    tier = _tier_from_score(confidence)
    return round(confidence, 4), tier


def _tier_from_score(score: float) -> ConfidenceTier:
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceTier.HIGH]:
        return ConfidenceTier.HIGH
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceTier.MEDIUM]:
        return ConfidenceTier.MEDIUM
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceTier.LOW]:
        return ConfidenceTier.LOW
    return ConfidenceTier.NONE


def is_low_confidence(confidence: float) -> bool:
    return confidence < CONFIDENCE_THRESHOLDS[ConfidenceTier.LOW]


def flag_if_low(confidence: float, label: str = "") -> str:
    if confidence < 0.3:
        return f"[LOW CONFIDENCE — {label}: verify this]"
    if confidence < 0.5:
        return f"[MODERATE CONFIDENCE — {label}]"
    return ""
