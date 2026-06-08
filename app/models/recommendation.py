"""Recommendation output model."""

from dataclasses import dataclass, field

from app.models.activity import Activity


@dataclass
class Recommendation:
    """Final recommendation returned by the decision system."""

    activity: Activity
    score: float
    reasoning: str
    warnings: list[str] = field(default_factory=list)
