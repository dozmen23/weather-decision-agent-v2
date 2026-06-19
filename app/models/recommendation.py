"""Recommendation output model."""

from dataclasses import dataclass, field

from app.models.activity import Activity
from app.models.venue import Venue, VenueFilterTrace


@dataclass
class RecommendationScoreBreakdown:
    """User-facing score components for a final recommendation."""

    weather_safety: float = 0.0
    preference_match: float = 0.0
    comfort_match: float = 0.0
    practicality: float = 0.0
    total_score: float = 0.0


@dataclass
class Recommendation:
    """Final recommendation returned by the decision system."""

    activity: Activity
    score: float
    reasoning: str
    score_breakdown: RecommendationScoreBreakdown = field(
        default_factory=RecommendationScoreBreakdown
    )
    warnings: list[str] = field(default_factory=list)
    venues: list[Venue] = field(default_factory=list)
    venue_filter_trace: list[VenueFilterTrace] = field(default_factory=list)
