"""User preference model."""

from dataclasses import dataclass


@dataclass
class UserPreferences:
    """User constraints and preferences for activity recommendations."""

    preferred_activity_type: str
    prefers_outdoor: bool
    min_temperature_celsius: float
    max_temperature_celsius: float
    max_precipitation_probability_percent: int
    max_wind_speed_kmh: float
