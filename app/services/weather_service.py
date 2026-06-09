"""Weather tool backed by the Open-Meteo geocoding and forecast APIs."""

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.weather_data import WeatherData


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

JsonFetcher = Callable[[str], dict[str, Any]]


class WeatherServiceError(RuntimeError):
    """Raised when weather data cannot be retrieved or normalized."""


@dataclass(frozen=True)
class Location:
    """Resolved geographic location used for a forecast request."""

    name: str
    country: str
    latitude: float
    longitude: float

    @property
    def display_name(self) -> str:
        """Return a readable city and country label."""
        return f"{self.name}, {self.country}" if self.country else self.name


class WeatherService:
    """Resolve a city and return normalized current weather information."""

    def __init__(self, json_fetcher: JsonFetcher | None = None) -> None:
        self._json_fetcher = json_fetcher or _fetch_json

    def get_current_weather(self, city: str) -> WeatherData:
        """Return current normalized weather for the requested city."""
        normalized_city = city.strip()
        if len(normalized_city) < 2:
            raise WeatherServiceError("City name must contain at least two characters.")

        location = self._resolve_location(normalized_city)
        forecast = self._fetch_forecast(location)
        return self._normalize_weather(location, forecast)

    def _resolve_location(self, city: str) -> Location:
        query = urlencode(
            {
                "name": city,
                "count": 1,
                "language": "en",
                "format": "json",
            }
        )
        payload = self._json_fetcher(f"{GEOCODING_URL}?{query}")
        results = payload.get("results")

        if not isinstance(results, list) or not results:
            raise WeatherServiceError(f"No location was found for '{city}'.")

        first_result = results[0]
        if not isinstance(first_result, dict):
            raise WeatherServiceError("Geocoding service returned an invalid location.")

        try:
            return Location(
                name=str(first_result["name"]),
                country=str(first_result.get("country", "")),
                latitude=float(first_result["latitude"]),
                longitude=float(first_result["longitude"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherServiceError(
                "Geocoding service returned incomplete location data."
            ) from exc

    def _fetch_forecast(self, location: Location) -> dict[str, Any]:
        query = urlencode(
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": (
                    "temperature_2m,precipitation_probability,"
                    "weather_code,wind_speed_10m"
                ),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
            }
        )
        return self._json_fetcher(f"{FORECAST_URL}?{query}")

    @staticmethod
    def _normalize_weather(
        location: Location,
        forecast: dict[str, Any],
    ) -> WeatherData:
        current = forecast.get("current")
        if not isinstance(current, dict):
            raise WeatherServiceError(
                "Forecast service did not return current weather data."
            )

        try:
            weather_code = int(current["weather_code"])
            return WeatherData(
                city=location.display_name,
                temperature_celsius=float(current["temperature_2m"]),
                precipitation_probability_percent=int(
                    current["precipitation_probability"]
                ),
                wind_speed_kmh=float(current["wind_speed_10m"]),
                condition=_weather_condition(weather_code),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherServiceError(
                "Forecast service returned incomplete current weather data."
            ) from exc


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"User-Agent": "weather-decision-agent/0.1"},
    )

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise WeatherServiceError(
            f"Weather provider returned HTTP status {exc.code}."
        ) from exc
    except URLError as exc:
        raise WeatherServiceError(
            "Weather provider could not be reached."
        ) from exc
    except json.JSONDecodeError as exc:
        raise WeatherServiceError(
            "Weather provider returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise WeatherServiceError("Weather provider returned an invalid response.")

    if payload.get("error") is True:
        reason = payload.get("reason", "Unknown provider error.")
        raise WeatherServiceError(f"Weather provider error: {reason}")

    return payload


def _weather_condition(weather_code: int) -> str:
    if weather_code == 0:
        return "Clear sky"
    if weather_code in {1, 2, 3}:
        return "Partly cloudy"
    if weather_code in {45, 48}:
        return "Foggy"
    if weather_code in {51, 53, 55, 56, 57}:
        return "Drizzle"
    if weather_code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "Rainy"
    if weather_code in {71, 73, 75, 77, 85, 86}:
        return "Snowy"
    if weather_code in {95, 96, 99}:
        return "Thunderstorm"
    return "Unknown"
