"""User preference model."""

from dataclasses import dataclass

from app.models.activity import ActivityIntensity, CostLevel


@dataclass
class UserPreferences:
    """User constraints and preferences for activity recommendations."""

    preferred_activity_type: str
    prefers_outdoor: bool
    min_temperature_celsius: float
    max_temperature_celsius: float
    max_precipitation_probability_percent: int
    max_wind_speed_kmh: float
    max_cost_level: CostLevel = CostLevel.HIGH
    max_duration_minutes: int = 240
    preferred_intensity: ActivityIntensity | None = None
    avoid_reservations: bool = False
    suitable_for: str | None = None
    indoor_feedback_penalty: float = 0.0
