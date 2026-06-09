"""Tests for the Open-Meteo weather service."""

import unittest
from urllib.parse import parse_qs, urlparse

from app.services.weather_service import (
    FORECAST_URL,
    GEOCODING_URL,
    WeatherService,
    WeatherServiceError,
)


class WeatherServiceTests(unittest.TestCase):
    def test_city_is_resolved_and_forecast_is_normalized(self) -> None:
        requested_urls: list[str] = []

        def fake_fetcher(url: str) -> dict[str, object]:
            requested_urls.append(url)
            if url.startswith(GEOCODING_URL):
                return {
                    "results": [
                        {
                            "name": "Istanbul",
                            "country": "Türkiye",
                            "latitude": 41.0138,
                            "longitude": 28.9497,
                        }
                    ]
                }
            if url.startswith(FORECAST_URL):
                return {
                    "current": {
                        "temperature_2m": 24.6,
                        "precipitation_probability": 20,
                        "weather_code": 2,
                        "wind_speed_10m": 13.4,
                    }
                }
            self.fail(f"Unexpected URL: {url}")

        weather = WeatherService(fake_fetcher).get_current_weather(" Istanbul ")

        self.assertEqual(weather.city, "Istanbul, Türkiye")
        self.assertEqual(weather.temperature_celsius, 24.6)
        self.assertEqual(weather.precipitation_probability_percent, 20)
        self.assertEqual(weather.wind_speed_kmh, 13.4)
        self.assertEqual(weather.condition, "Partly cloudy")
        self.assertEqual(len(requested_urls), 2)

        forecast_query = parse_qs(urlparse(requested_urls[1]).query)
        self.assertEqual(forecast_query["latitude"], ["41.0138"])
        self.assertEqual(forecast_query["wind_speed_unit"], ["kmh"])

    def test_unknown_city_raises_clear_error(self) -> None:
        service = WeatherService(lambda _: {"results": []})

        with self.assertRaisesRegex(WeatherServiceError, "No location was found"):
            service.get_current_weather("NotARealCity")

    def test_short_city_name_is_rejected_before_api_call(self) -> None:
        calls = 0

        def fake_fetcher(_: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}

        with self.assertRaisesRegex(WeatherServiceError, "at least two"):
            WeatherService(fake_fetcher).get_current_weather("I")

        self.assertEqual(calls, 0)

    def test_incomplete_forecast_is_rejected(self) -> None:
        responses = iter(
            [
                {
                    "results": [
                        {
                            "name": "Istanbul",
                            "country": "Türkiye",
                            "latitude": 41.0138,
                            "longitude": 28.9497,
                        }
                    ]
                },
                {"current": {"temperature_2m": 20}},
            ]
        )

        with self.assertRaisesRegex(
            WeatherServiceError,
            "incomplete current weather",
        ):
            WeatherService(lambda _: next(responses)).get_current_weather("Istanbul")

    def test_weather_codes_are_converted_to_readable_conditions(self) -> None:
        responses = iter(
            [
                {
                    "results": [
                        {
                            "name": "Istanbul",
                            "country": "Türkiye",
                            "latitude": 41.0138,
                            "longitude": 28.9497,
                        }
                    ]
                },
                {
                    "current": {
                        "temperature_2m": 18,
                        "precipitation_probability": 80,
                        "weather_code": 95,
                        "wind_speed_10m": 40,
                    }
                },
            ]
        )

        weather = WeatherService(lambda _: next(responses)).get_current_weather(
            "Istanbul"
        )

        self.assertEqual(weather.condition, "Thunderstorm")


if __name__ == "__main__":
    unittest.main()
