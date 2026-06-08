"""Weather data model."""

from dataclasses import dataclass


@dataclass
class WeatherData:
    """Normalized weather information used by the decision system."""

    city: str
    temperature_celsius: float
    precipitation_probability_percent: int
    wind_speed_kmh: float
    condition: str
