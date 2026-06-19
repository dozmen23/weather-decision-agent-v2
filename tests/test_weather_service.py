"""Tests for the Open-Meteo weather service."""

import unittest
from datetime import date
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

    def test_coordinates_skip_geocoding_and_fetch_current_weather(self) -> None:
        requested_urls: list[str] = []

        def fake_fetcher(url: str) -> dict[str, object]:
            requested_urls.append(url)
            if url.startswith(FORECAST_URL):
                return {
                    "current": {
                        "temperature_2m": 21.0,
                        "precipitation_probability": 15,
                        "weather_code": 1,
                        "wind_speed_10m": 9.5,
                    }
                }
            self.fail(f"Unexpected URL: {url}")

        weather = WeatherService(fake_fetcher).get_current_weather_for_coordinates(
            41.0138,
            28.9497,
            label="Pinned Istanbul",
        )

        self.assertEqual(weather.city, "Pinned Istanbul")
        self.assertEqual(weather.condition, "Partly cloudy")
        self.assertEqual(len(requested_urls), 1)
        query = parse_qs(urlparse(requested_urls[0]).query)
        self.assertEqual(query["latitude"], ["41.0138"])
        self.assertEqual(query["longitude"], ["28.9497"])

    def test_invalid_coordinates_are_rejected_before_api_call(self) -> None:
        calls = 0

        def fake_fetcher(_: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}

        with self.assertRaisesRegex(WeatherServiceError, "Latitude"):
            WeatherService(fake_fetcher).get_current_weather_for_coordinates(
                120,
                28.9497,
            )

        self.assertEqual(calls, 0)

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

    def test_seven_day_forecast_is_requested_and_normalized(self) -> None:
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
                    "daily": {
                        "time": ["2026-06-12", "2026-06-13"],
                        "weather_code": [2, 61],
                        "temperature_2m_max": [28.0, 24.0],
                        "temperature_2m_min": [18.0, 16.0],
                        "precipitation_probability_max": [20, 75],
                        "wind_speed_10m_max": [12.5, 22.0],
                    }
                }
            self.fail(f"Unexpected URL: {url}")

        forecast = WeatherService(fake_fetcher).get_daily_forecast(
            "Istanbul",
            forecast_days=7,
        )

        self.assertEqual(len(forecast), 2)
        self.assertEqual(forecast[0].forecast_date, date(2026, 6, 12))
        self.assertEqual(forecast[0].temperature_celsius, 23.0)
        self.assertEqual(forecast[0].minimum_temperature_celsius, 18.0)
        self.assertEqual(forecast[0].maximum_temperature_celsius, 28.0)
        self.assertEqual(forecast[1].condition, "Rainy")

        query = parse_qs(urlparse(requested_urls[1]).query)
        self.assertEqual(query["forecast_days"], ["7"])
        self.assertIn("temperature_2m_max", query["daily"][0])
        self.assertEqual(query["timezone"], ["auto"])

    def test_coordinate_daily_forecast_is_requested_and_normalized(self) -> None:
        requested_urls: list[str] = []

        def fake_fetcher(url: str) -> dict[str, object]:
            requested_urls.append(url)
            if url.startswith(FORECAST_URL):
                return {
                    "daily": {
                        "time": ["2026-06-12"],
                        "weather_code": [0],
                        "temperature_2m_max": [27.0],
                        "temperature_2m_min": [17.0],
                        "precipitation_probability_max": [15],
                        "wind_speed_10m_max": [10.0],
                    }
                }
            self.fail(f"Unexpected URL: {url}")

        forecast = WeatherService(fake_fetcher).get_daily_forecast_for_coordinates(
            41.0138,
            28.9497,
            label="Pinned Istanbul",
            forecast_days=7,
        )

        self.assertEqual(forecast[0].city, "Pinned Istanbul")
        self.assertEqual(forecast[0].forecast_date, date(2026, 6, 12))
        query = parse_qs(urlparse(requested_urls[0]).query)
        self.assertEqual(query["latitude"], ["41.0138"])
        self.assertEqual(query["forecast_days"], ["7"])

    def test_invalid_forecast_day_count_is_rejected_before_api_call(self) -> None:
        calls = 0

        def fake_fetcher(_: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}

        with self.assertRaisesRegex(WeatherServiceError, "between 1 and 16"):
            WeatherService(fake_fetcher).get_daily_forecast(
                "Istanbul",
                forecast_days=17,
            )

        self.assertEqual(calls, 0)

    def test_weather_for_date_selects_matching_daily_forecast(self) -> None:
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
                    "daily": {
                        "time": ["2026-06-12", "2026-06-13"],
                        "weather_code": [0, 61],
                        "temperature_2m_max": [28, 22],
                        "temperature_2m_min": [18, 14],
                        "precipitation_probability_max": [10, 80],
                        "wind_speed_10m_max": [8, 20],
                    }
                },
            ]
        )

        weather = WeatherService(
            lambda _: next(responses)
        ).get_weather_for_date(
            "Istanbul",
            date(2026, 6, 13),
        )

        self.assertEqual(weather.forecast_date, date(2026, 6, 13))
        self.assertEqual(weather.condition, "Rainy")
        self.assertEqual(weather.temperature_celsius, 18)

    def test_weather_for_unavailable_date_is_rejected(self) -> None:
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
                    "daily": {
                        "time": ["2026-06-12"],
                        "weather_code": [0],
                        "temperature_2m_max": [28],
                        "temperature_2m_min": [18],
                        "precipitation_probability_max": [10],
                        "wind_speed_10m_max": [8],
                    }
                },
            ]
        )

        with self.assertRaisesRegex(
            WeatherServiceError,
            "No forecast is available",
        ):
            WeatherService(lambda _: next(responses)).get_weather_for_date(
                "Istanbul",
                date(2026, 6, 20),
            )

    def test_incomplete_daily_forecast_is_rejected(self) -> None:
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
                    "daily": {
                        "time": ["2026-06-12"],
                        "temperature_2m_max": [28.0],
                    }
                },
            ]
        )

        with self.assertRaisesRegex(
            WeatherServiceError,
            "incomplete daily weather",
        ):
            WeatherService(lambda _: next(responses)).get_daily_forecast(
                "Istanbul"
            )


if __name__ == "__main__":
    unittest.main()
