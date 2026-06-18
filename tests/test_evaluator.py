"""Tests for independent deterministic result evaluation."""

import unittest

from app.agent.decision_agent import (
    AgentResult,
    AgentTraceStep,
    DecisionAgent,
)
from app.agent.planner import AgentAction
from app.models.activity import Activity
from app.models.recommendation import Recommendation
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from evaluation.evaluator import DeterministicEvaluator, EvaluationVerdict


class StubWeatherTool:
    def __init__(self, weather: WeatherData) -> None:
        self.weather = weather

    def get_current_weather(self, _: str) -> WeatherData:
        return self.weather


class StubActivityTool:
    def __init__(self, activities: list[Activity]) -> None:
        self.activities = activities

    def find_candidates(
        self,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> list[Activity]:
        candidates = self.activities
        if activity_type is not None:
            candidates = [
                activity
                for activity in candidates
                if activity.activity_type.casefold() == activity_type.casefold()
            ]
        if is_outdoor is not None:
            candidates = [
                activity
                for activity in candidates
                if activity.is_outdoor is is_outdoor
            ]
        return candidates

    def find_similar_candidates(
        self,
        activity_type: str,
        is_outdoor: bool | None = None,
        limit: int = 8,
    ) -> list[Activity]:
        candidates = self.find_candidates(is_outdoor=is_outdoor)
        exact_matches = [
            activity
            for activity in candidates
            if activity.activity_type.casefold() == activity_type.casefold()
        ]
        return (exact_matches or candidates)[:limit]


class DeterministicEvaluatorTests(unittest.TestCase):
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
            "Park Walk",
            "walking",
            True,
            8,
            32,
            45,
            30,
        )
        self.museum = Activity(
            "Museum Visit",
            "culture",
            False,
            -20,
            50,
            100,
            100,
        )
        self.evaluator = DeterministicEvaluator()

    def test_valid_agent_result_is_approved(self) -> None:
        result = DecisionAgent(
            StubWeatherTool(WeatherData("Istanbul", 22.5, 5, 5, "Clear")),
            StubActivityTool([self.park_walk, self.museum]),
        ).run("Istanbul", self.preferences)

        report = self.evaluator.evaluate(result, self.preferences)

        self.assertEqual(report.verdict, EvaluationVerdict.APPROVED)
        self.assertTrue(report.system_behavior_valid)
        self.assertTrue(report.recommendation_success)
        self.assertEqual(report.quality_score, 100.0)

    def test_weather_fallback_result_is_approved_when_consistent(self) -> None:
        result = DecisionAgent(
            StubWeatherTool(
                WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")
            ),
            StubActivityTool([self.park_walk, self.museum]),
        ).run("Istanbul", self.preferences)

        report = self.evaluator.evaluate(result, self.preferences)

        self.assertEqual(report.verdict, EvaluationVerdict.APPROVED)
        self.assertTrue(result.used_safe_fallback)
        self.assertEqual(result.recommendations[0].activity.name, "Museum Visit")

    def test_tampered_unsafe_recommendation_is_rejected(self) -> None:
        weather = WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")
        result = AgentResult(
            status="completed",
            weather=weather,
            recommendations=[
                Recommendation(
                    activity=self.park_walk,
                    score=90,
                    reasoning="a; b; c; d; e",
                )
            ],
            trace=[
                AgentTraceStep(AgentAction.FETCH_WEATHER, "weather"),
                AgentTraceStep(AgentAction.SCORE_CANDIDATES, "scored"),
                AgentTraceStep(AgentAction.FINALIZE, "finalized"),
            ],
        )

        report = self.evaluator.evaluate(result, self.preferences)

        self.assertEqual(report.verdict, EvaluationVerdict.REJECTED)
        self.assertFalse(report.system_behavior_valid)
        self.assertIn(
            "safety_and_warning_integrity",
            [check.name for check in report.failed_checks],
        )

    def test_altered_score_is_rejected(self) -> None:
        result = DecisionAgent(
            StubWeatherTool(WeatherData("Istanbul", 22.5, 5, 5, "Clear")),
            StubActivityTool([self.park_walk]),
        ).run("Istanbul", self.preferences)
        result.recommendations[0].score = 99.0

        report = self.evaluator.evaluate(result, self.preferences)

        self.assertEqual(report.verdict, EvaluationVerdict.REJECTED)
        self.assertIn(
            "score_integrity",
            [check.name for check in report.failed_checks],
        )

    def test_safe_stop_is_valid_but_not_recommendation_success(self) -> None:
        result = DecisionAgent(
            StubWeatherTool(
                WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")
            ),
            StubActivityTool([self.park_walk]),
        ).run("Istanbul", self.preferences)

        report = self.evaluator.evaluate(result, self.preferences)

        self.assertEqual(report.verdict, EvaluationVerdict.NO_RECOMMENDATION)
        self.assertTrue(report.system_behavior_valid)
        self.assertFalse(report.recommendation_success)
        self.assertEqual(report.quality_score, 100.0)


if __name__ == "__main__":
    unittest.main()
