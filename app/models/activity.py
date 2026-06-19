"""Activity model."""

from dataclasses import dataclass, field
from enum import Enum


class ActivityIntensity(str, Enum):
    """Typical physical or mental effort required by an activity."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class CostLevel(str, Enum):
    """Coarse cost category used for filtering and practicality scoring."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WeatherSensitivity(str, Enum):
    """How strongly an activity depends on favorable weather."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class TransportEase(str, Enum):
    """How easy an activity type is to access before venue-level data exists."""

    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


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
    purpose: str = "general"
    intensity: ActivityIntensity = ActivityIntensity.MODERATE
    duration_minutes: int = 60
    cost_level: CostLevel = CostLevel.LOW
    weather_sensitivity: WeatherSensitivity = WeatherSensitivity.MODERATE
    requires_reservation: bool = False
    transport_ease: TransportEase = TransportEase.MODERATE
    suitable_for: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
