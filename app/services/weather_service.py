"""Weather tool backed by the Open-Meteo geocoding and forecast APIs."""

import json
from dataclasses import dataclass
from datetime import date
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
        location = self._resolve_location(self._normalize_city(city))
        forecast = self._fetch_forecast(location)
        return self._normalize_weather(location, forecast)

    def resolve_coordinates(self, city: str) -> tuple[float, float]:
        """Return the (latitude, longitude) geocoded for a city name."""
        location = self._resolve_location(self._normalize_city(city))
        return location.latitude, location.longitude

    def get_current_weather_for_coordinates(
        self,
        latitude: float,
        longitude: float,
        label: str = "Selected location",
    ) -> WeatherData:
        """Return current weather for a direct map/coordinate selection."""
        location = self._location_from_coordinates(latitude, longitude, label)
        forecast = self._fetch_forecast(location)
        return self._normalize_weather(location, forecast)

    def get_daily_forecast(
        self,
        city: str,
        forecast_days: int = 7,
    ) -> list[WeatherData]:
        """Return normalized daily forecasts for the requested city."""
        if not 1 <= forecast_days <= 16:
            raise WeatherServiceError(
                "Forecast day count must be between 1 and 16."
            )

        location = self._resolve_location(self._normalize_city(city))
        forecast = self._fetch_daily_forecast(location, forecast_days)
        return self._normalize_daily_forecast(location, forecast)

    def get_daily_forecast_for_coordinates(
        self,
        latitude: float,
        longitude: float,
        label: str = "Selected location",
        forecast_days: int = 7,
    ) -> list[WeatherData]:
        """Return daily forecasts for a direct map/coordinate selection."""
        if not 1 <= forecast_days <= 16:
            raise WeatherServiceError(
                "Forecast day count must be between 1 and 16."
            )

        location = self._location_from_coordinates(latitude, longitude, label)
        forecast = self._fetch_daily_forecast(location, forecast_days)
        return self._normalize_daily_forecast(location, forecast)

    def get_weather_for_date(
        self,
        city: str,
        target_date: date,
    ) -> WeatherData:
        """Return the daily forecast matching a specific date."""
        forecasts = self.get_daily_forecast(city, forecast_days=7)
        for weather in forecasts:
            if weather.forecast_date == target_date:
                return weather

        raise WeatherServiceError(
            f"No forecast is available for {target_date.isoformat()}."
        )

    def get_weather_for_coordinates_and_date(
        self,
        latitude: float,
        longitude: float,
        target_date: date,
        label: str = "Selected location",
    ) -> WeatherData:
        """Return one forecast day for a direct map/coordinate selection."""
        forecasts = self.get_daily_forecast_for_coordinates(
            latitude,
            longitude,
            label=label,
            forecast_days=7,
        )
        for weather in forecasts:
            if weather.forecast_date == target_date:
                return weather

        raise WeatherServiceError(
            f"No forecast is available for {target_date.isoformat()}."
        )

    @staticmethod
    def _normalize_city(city: str) -> str:
        normalized_city = city.strip()
        if len(normalized_city) < 2:
            raise WeatherServiceError(
                "City name must contain at least two characters."
            )
        return normalized_city

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

    @staticmethod
    def _location_from_coordinates(
        latitude: float,
        longitude: float,
        label: str,
    ) -> Location:
        try:
            normalized_latitude = float(latitude)
            normalized_longitude = float(longitude)
        except (TypeError, ValueError) as exc:
            raise WeatherServiceError("Coordinates must be numeric.") from exc

        if not -90 <= normalized_latitude <= 90:
            raise WeatherServiceError("Latitude must be between -90 and 90.")
        if not -180 <= normalized_longitude <= 180:
            raise WeatherServiceError("Longitude must be between -180 and 180.")

        normalized_label = label.strip() if label else "Selected location"
        return Location(
            name=normalized_label,
            country="",
            latitude=normalized_latitude,
            longitude=normalized_longitude,
        )

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

    def _fetch_daily_forecast(
        self,
        location: Location,
        forecast_days: int,
    ) -> dict[str, Any]:
        query = urlencode(
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,wind_speed_10m_max"
                ),
                "forecast_days": forecast_days,
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

    @staticmethod
    def _normalize_daily_forecast(
        location: Location,
        forecast: dict[str, Any],
    ) -> list[WeatherData]:
        daily = forecast.get("daily")
        if not isinstance(daily, dict):
            raise WeatherServiceError(
                "Forecast service did not return daily weather data."
            )

        required_fields = (
            "time",
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "wind_speed_10m_max",
        )
        values = [daily.get(field) for field in required_fields]
        if (
            any(not isinstance(value, list) for value in values)
            or not values[0]
            or len({len(value) for value in values}) != 1
        ):
            raise WeatherServiceError(
                "Forecast service returned incomplete daily weather data."
            )

        forecasts: list[WeatherData] = []
        try:
            for (
                day_text,
                weather_code,
                maximum_temperature,
                minimum_temperature,
                precipitation_probability,
                wind_speed,
            ) in zip(*values):
                minimum = float(minimum_temperature)
                maximum = float(maximum_temperature)
                forecasts.append(
                    WeatherData(
                        city=location.display_name,
                        # Use the daytime maximum as the decision temperature.
                        # A daily midpoint can understate summer heat and make
                        # activity suitability look milder than peak conditions.
                        temperature_celsius=maximum,
                        precipitation_probability_percent=int(
                            precipitation_probability
                        ),
                        wind_speed_kmh=float(wind_speed),
                        condition=_weather_condition(int(weather_code)),
                        forecast_date=date.fromisoformat(str(day_text)),
                        minimum_temperature_celsius=minimum,
                        maximum_temperature_celsius=maximum,
                    )
                )
        except (TypeError, ValueError) as exc:
            raise WeatherServiceError(
                "Forecast service returned invalid daily weather data."
            ) from exc

        return forecasts


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
