"""Tests for explainable activity scoring and ranking."""

import unittest

from app.core.scoring import rank_activities, score_activity
from app.models.activity import Activity
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


class ActivityScoringTests(unittest.TestCase):
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
        self.museum = Activity(
            name="Museum visit",
            activity_type="culture",
            is_outdoor=False,
            min_temperature_celsius=-20,
            max_temperature_celsius=50,
            max_precipitation_probability_percent=100,
            max_wind_speed_kmh=100,
        )

    def test_matching_activity_receives_explainable_component_scores(self) -> None:
        weather = WeatherData("Istanbul", 22.5, 0, 0, "Clear")

        result = score_activity(weather, self.preferences, self.park_walk)

        self.assertTrue(result.is_eligible)
        self.assertEqual(result.total_score, 100.0)
        self.assertEqual(len(result.explanations), 5)

    def test_weather_risk_reduces_score_before_reaching_hard_limit(self) -> None:
        calm_weather = WeatherData("Istanbul", 22.5, 5, 5, "Clear")
        marginal_weather = WeatherData("Istanbul", 29, 35, 22, "Cloudy")

        calm_result = score_activity(
            calm_weather,
            self.preferences,
            self.park_walk,
        )
        marginal_result = score_activity(
            marginal_weather,
            self.preferences,
            self.park_walk,
        )

        self.assertTrue(marginal_result.is_eligible)
        self.assertGreater(calm_result.total_score, marginal_result.total_score)

    def test_ineligible_activity_is_not_ranked(self) -> None:
        rainy_weather = WeatherData("Istanbul", 22, 80, 10, "Rainy")

        ranked = rank_activities(
            rainy_weather,
            self.preferences,
            [self.park_walk, self.museum],
        )

        self.assertEqual([result.activity.name for result in ranked], ["Museum visit"])

    def test_ranking_prefers_better_user_and_weather_match(self) -> None:
        weather = WeatherData("Istanbul", 22.5, 5, 5, "Clear")

        ranked = rank_activities(
            weather,
            self.preferences,
            [self.museum, self.park_walk],
        )

        self.assertEqual(ranked[0].activity.name, "Park walk")
        self.assertGreater(ranked[0].total_score, ranked[1].total_score)


if __name__ == "__main__":
    unittest.main()
