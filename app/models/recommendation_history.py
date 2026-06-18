"""Recommendation history and user feedback models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class FeedbackValue(str, Enum):
    """Supported user feedback labels for a recommendation run."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass
class RecommendationHistoryItem:
    """Compact persisted representation of one recommendation."""

    activity_name: str
    activity_type: str
    is_outdoor: bool
    score: float


@dataclass
class RecommendationHistoryRecord:
    """One persisted recommendation workflow run."""

    record_id: str
    created_at: str
    city: str
    target_date: str | None
    status: str
    used_safe_fallback: bool
    used_generated_candidates: bool
    weather: dict[str, object]
    preferences: dict[str, object]
    recommendations: list[RecommendationHistoryItem] = field(default_factory=list)
    feedback: FeedbackValue | None = None
    feedback_note: str = ""


def new_history_record_id() -> str:
    """Return an opaque id for a history record."""
    return str(uuid4())


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for persistence."""
    return datetime.now(timezone.utc).isoformat()
