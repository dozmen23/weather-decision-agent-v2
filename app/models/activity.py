"""Activity model."""

from dataclasses import dataclass


@dataclass
class Activity:
    """Candidate activity that can be recommended by the agent."""

    name: str
    activity_type: str
    is_outdoor: bool
    min_temperature_celsius: float
    max_temperature_celsius: float
    max_precipitation_probability_percent: int
    max_wind_speed_kmh: float
