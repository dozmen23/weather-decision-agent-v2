"""Weather data model."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class WeatherSeverity(str, Enum):
    """General weather risk level derived from normalized weather data."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


@dataclass
class WeatherData:
    """Normalized weather information used by the decision system."""

    city: str
    temperature_celsius: float
    precipitation_probability_percent: int
    wind_speed_kmh: float
    condition: str
    forecast_date: date | None = None
    minimum_temperature_celsius: float | None = None
    maximum_temperature_celsius: float | None = None
    severity_level: WeatherSeverity = field(init=False)

    def __post_init__(self) -> None:
        self.severity_level = classify_weather_severity(
            temperature_celsius=self.temperature_celsius,
            precipitation_probability_percent=(
                self.precipitation_probability_percent
            ),
            wind_speed_kmh=self.wind_speed_kmh,
            condition=self.condition,
        )


def classify_weather_severity(
    *,
    temperature_celsius: float,
    precipitation_probability_percent: int,
    wind_speed_kmh: float,
    condition: str,
) -> WeatherSeverity:
    """Return a coarse risk level from weather measurements and condition."""
    normalized_condition = condition.strip().casefold()
    condition_tokens = normalized_condition.replace("-", " ").split()

    if (
        "thunderstorm" in normalized_condition
        or "storm" in normalized_condition
        or wind_speed_kmh >= 50
        or precipitation_probability_percent >= 85
        or temperature_celsius <= -5
        or temperature_celsius >= 40
    ):
        return WeatherSeverity.SEVERE

    if (
        wind_speed_kmh >= 35
        or precipitation_probability_percent >= 65
        or temperature_celsius <= 0
        or temperature_celsius >= 35
        or {"rainy", "snowy"} & set(condition_tokens)
    ):
        return WeatherSeverity.HIGH

    if (
        wind_speed_kmh >= 20
        or precipitation_probability_percent >= 35
        or temperature_celsius <= 5
        or temperature_celsius >= 32
        or {"drizzle", "foggy", "windy"} & set(condition_tokens)
    ):
        return WeatherSeverity.MODERATE

    return WeatherSeverity.LOW
