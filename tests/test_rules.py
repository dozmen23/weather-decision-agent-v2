"""Tests for deterministic activity eligibility rules."""

import unittest

from app.core.rules import evaluate_activity
from app.models.activity import Activity, ActivityIntensity, CostLevel
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


class ActivityRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preferences = UserPreferences(
            preferred_activity_type="walking",
            prefers_outdoor=True,
            min_temperature_celsius=15,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        self.park_walk = Activity(
            name="Park walk",
            activity_type="walking",
            is_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=32,
            max_precipitation_probability_percent=50,
            max_wind_speed_kmh=30,
        )

    def test_suitable_outdoor_activity_is_eligible(self) -> None:
        weather = WeatherData("Istanbul", 24, 20, 12, "Partly cloudy")

        result = evaluate_activity(weather, self.preferences, self.park_walk)

        self.assertTrue(result.is_eligible)
        self.assertEqual(result.failed_rules, [])
        self.assertEqual(result.warnings, [])

    def test_heavy_rain_eliminates_outdoor_activity(self) -> None:
        weather = WeatherData("Istanbul", 22, 80, 10, "Rainy")

        result = evaluate_activity(weather, self.preferences, self.park_walk)

        self.assertFalse(result.is_eligible)
        self.assertIn(
            "Precipitation risk is too high for the activity.",
            result.failed_rules,
        )
        self.assertIn(
            "Precipitation risk exceeds the user's limit.",
            result.failed_rules,
        )

    def test_strong_wind_eliminates_outdoor_activity(self) -> None:
        weather = WeatherData("Istanbul", 20, 10, 45, "Windy")

        result = evaluate_activity(weather, self.preferences, self.park_walk)

        self.assertFalse(result.is_eligible)
        self.assertEqual(len(result.failed_rules), 2)

    def test_severe_weather_eliminates_outdoor_activity(self) -> None:
        permissive_walk = Activity(
            name="All weather walk",
            activity_type="walking",
            is_outdoor=True,
            min_temperature_celsius=-20,
            max_temperature_celsius=50,
            max_precipitation_probability_percent=100,
            max_wind_speed_kmh=100,
        )
        weather = WeatherData("Istanbul", 22, 20, 10, "Thunderstorm")

        result = evaluate_activity(weather, self.preferences, permissive_walk)

        self.assertFalse(result.is_eligible)
        self.assertIn(
            "Weather severity is too high for outdoor activities.",
            result.failed_rules,
        )

    def test_indoor_activity_is_not_eliminated_by_bad_weather(self) -> None:
        museum = Activity(
            name="Museum visit",
            activity_type="culture",
            is_outdoor=False,
            min_temperature_celsius=-20,
            max_temperature_celsius=50,
            max_precipitation_probability_percent=100,
            max_wind_speed_kmh=100,
        )
        weather = WeatherData("Istanbul", 2, 95, 60, "Stormy")

        result = evaluate_activity(weather, self.preferences, museum)

        self.assertTrue(result.is_eligible)
        self.assertEqual(len(result.warnings), 2)

    def test_practical_preferences_filter_activity(self) -> None:
        preferences = UserPreferences(
            preferred_activity_type="sports",
            prefers_outdoor=False,
            min_temperature_celsius=10,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
            max_cost_level=CostLevel.LOW,
            max_duration_minutes=60,
            preferred_intensity=ActivityIntensity.MODERATE,
            avoid_reservations=True,
            suitable_for="families",
        )
        activity = Activity(
            name="Premium court session",
            activity_type="sports",
            is_outdoor=False,
            min_temperature_celsius=-20,
            max_temperature_celsius=50,
            max_precipitation_probability_percent=100,
            max_wind_speed_kmh=100,
            intensity=ActivityIntensity.HIGH,
            duration_minutes=90,
            cost_level=CostLevel.MEDIUM,
            requires_reservation=True,
            suitable_for=("friends", "teams"),
        )
        weather = WeatherData("Istanbul", 22, 5, 5, "Clear sky")

        result = evaluate_activity(weather, preferences, activity)

        self.assertFalse(result.is_eligible)
        self.assertIn(
            "Activity cost exceeds the user's budget preference.",
            result.failed_rules,
        )
        self.assertIn(
            "Activity duration exceeds the user's time preference.",
            result.failed_rules,
        )
        self.assertIn("Activity requires a reservation.", result.failed_rules)
        self.assertIn(
            "Activity intensity exceeds the user's preference.",
            result.failed_rules,
        )
        self.assertIn(
            "Activity is not suitable for the selected company.",
            result.failed_rules,
        )


if __name__ == "__main__":
    unittest.main()
