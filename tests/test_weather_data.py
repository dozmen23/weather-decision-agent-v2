"""Tests for normalized weather metadata."""

import unittest

from app.models.weather_data import (
    WeatherData,
    WeatherSeverity,
    classify_weather_severity,
)


class WeatherSeverityTests(unittest.TestCase):
    def test_clear_mild_weather_is_low_risk(self) -> None:
        weather = WeatherData("Istanbul", 22, 5, 8, "Clear sky")

        self.assertIs(weather.severity_level, WeatherSeverity.LOW)

    def test_drizzle_or_marginal_values_are_moderate_risk(self) -> None:
        severity = classify_weather_severity(
            temperature_celsius=24,
            precipitation_probability_percent=25,
            wind_speed_kmh=8,
            condition="Drizzle",
        )

        self.assertIs(severity, WeatherSeverity.MODERATE)

    def test_heavy_rain_is_high_risk_before_severe_threshold(self) -> None:
        severity = classify_weather_severity(
            temperature_celsius=18,
            precipitation_probability_percent=70,
            wind_speed_kmh=15,
            condition="Rainy",
        )

        self.assertIs(severity, WeatherSeverity.HIGH)

    def test_thunderstorm_is_severe_regardless_of_other_values(self) -> None:
        severity = classify_weather_severity(
            temperature_celsius=22,
            precipitation_probability_percent=20,
            wind_speed_kmh=10,
            condition="Thunderstorm",
        )

        self.assertIs(severity, WeatherSeverity.SEVERE)


if __name__ == "__main__":
    unittest.main()
