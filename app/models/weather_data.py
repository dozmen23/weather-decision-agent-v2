"""Weather data model."""

from dataclasses import dataclass
from datetime import date


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
