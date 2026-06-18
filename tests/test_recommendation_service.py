"""Tests for the end-to-end recommendation workflow service."""

import unittest
from datetime import date
from typing import Any

from app.agent.decision_agent import AgentResult, DecisionAgent
from app.llm.judge_service import LLMJudgeVerdict
from app.models.activity import Activity
from app.models.recommendation import Recommendation
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from app.services.recommendation_service import RecommendationService


class FakeStructuredLLMClient:
    def __init__(self) -> None:
        self.schemas: list[str] = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.schemas.append(schema_name)
        if schema_name == "recommendation_explanation":
            return {
                "summary": "Park Walk is the best verified option.",
                "weather_context": "The weather is mild and dry.",
                "recommendation_details": [
                    {
                        "activity_name": "Park Walk",
                        "explanation": (
                            "It matches the preference and safety limits."
                        ),
                    }
                ],
                "fallback_note": "",
            }
        if schema_name == "llm_judge_report":
            return {
                "verdict": "approve",
                "confidence": 0.95,
                "rationale": "The verified recommendation is relevant and clear.",
                "concerns": [],
            }
        raise AssertionError(f"Unexpected schema: {schema_name}")


class StubWeatherTool:
    def get_current_weather(self, _: str) -> WeatherData:
        return WeatherData("Istanbul", 22.5, 5, 5, "Clear sky")

    def get_weather_for_date(
        self,
        _: str,
        target_date: date,
    ) -> WeatherData:
        return WeatherData(
            "Istanbul",
            22.5,
            5,
            5,
            "Clear sky",
            forecast_date=target_date,
        )


class StubActivityTool:
    def __init__(self) -> None:
        self.activity = Activity(
            "Park Walk",
            "walking",
            True,
            8,
            32,
            45,
            30,
        )

    def find_candidates(
        self,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> list[Activity]:
        if (
            activity_type is not None
            and activity_type.casefold() != self.activity.activity_type
        ):
            return []
        if is_outdoor is not None and is_outdoor is not self.activity.is_outdoor:
            return []
        return [self.activity]

    def find_similar_candidates(
        self,
        activity_type: str,
        is_outdoor: bool | None = None,
        limit: int = 8,
    ) -> list[Activity]:
        return self.find_candidates(
            activity_type=activity_type,
            is_outdoor=is_outdoor,
        )[:limit]


class InvalidAgent:
    def run(
        self,
        city: str,
        preferences: UserPreferences,
        recommendation_limit: int = 3,
    ) -> AgentResult:
        activity = Activity(
            "Unsafe Walk",
            "walking",
            True,
            10,
            30,
            20,
            20,
        )
        return AgentResult(
            status="completed",
            weather=WeatherData(city, 18, 90, 45, "Thunderstorm"),
            recommendations=[
                Recommendation(
                    activity=activity,
                    score=99,
                    reasoning="a; b; c; d; e",
                )
            ],
        )


class RecommendationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preferences = UserPreferences(
            preferred_activity_type="walking",
            prefers_outdoor=True,
            min_temperature_celsius=15,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )

    def test_valid_result_is_explained_and_second_checked(self) -> None:
        llm_client = FakeStructuredLLMClient()
        service = RecommendationService(
            agent=DecisionAgent(StubWeatherTool(), StubActivityTool()),
            llm_client=llm_client,
        )

        result = service.recommend("Istanbul", self.preferences)

        self.assertEqual(result.agent_result.status, "completed")
        self.assertIsNotNone(result.explanation)
        self.assertEqual(
            result.llm_judgment.verdict,
            LLMJudgeVerdict.APPROVE,
        )
        self.assertEqual(
            llm_client.schemas,
            ["recommendation_explanation", "llm_judge_report"],
        )

    def test_workflow_can_run_without_llm(self) -> None:
        service = RecommendationService(
            agent=DecisionAgent(StubWeatherTool(), StubActivityTool())
        )

        result = service.recommend("Istanbul", self.preferences)

        self.assertTrue(result.deterministic_evaluation.system_behavior_valid)
        self.assertIsNone(result.explanation)
        self.assertIsNone(result.llm_judgment)

    def test_deterministic_rejection_prevents_llm_calls(self) -> None:
        llm_client = FakeStructuredLLMClient()
        service = RecommendationService(
            agent=InvalidAgent(),
            llm_client=llm_client,
        )

        result = service.recommend("Istanbul", self.preferences)

        self.assertFalse(
            result.deterministic_evaluation.system_behavior_valid
        )
        self.assertIsNone(result.explanation)
        self.assertIsNone(result.llm_judgment)
        self.assertEqual(llm_client.schemas, [])

    def test_workflow_passes_selected_date_to_agent(self) -> None:
        selected_date = date(2026, 6, 15)
        service = RecommendationService(
            agent=DecisionAgent(StubWeatherTool(), StubActivityTool())
        )

        result = service.recommend(
            "Istanbul",
            self.preferences,
            target_date=selected_date,
        )

        self.assertEqual(
            result.agent_result.weather.forecast_date,
            selected_date,
        )


if __name__ == "__main__":
    unittest.main()
