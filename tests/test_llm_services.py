"""Tests for provider-independent LLM explanation and judge services."""

import json
import unittest
from datetime import date
from typing import Any

from app.agent.decision_agent import DecisionAgent
from app.llm.client import LLMServiceError
from app.llm.explanation_service import ExplanationService
from app.llm.judge_service import LLMJudgeService, LLMJudgeVerdict
from app.models.activity import Activity
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from evaluation.evaluator import DeterministicEvaluator


class FakeStructuredLLMClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema_name": schema_name,
                "json_schema": json_schema,
            }
        )
        return next(self.responses)


class StubWeatherTool:
    def get_current_weather(self, _: str) -> WeatherData:
        return WeatherData("Istanbul", 22.5, 5, 5, "Clear sky")


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
        if (
            is_outdoor is not None
            and is_outdoor is not self.activity.is_outdoor
        ):
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


class LLMServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preferences = UserPreferences(
            preferred_activity_type="walking",
            prefers_outdoor=True,
            min_temperature_celsius=15,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        self.result = DecisionAgent(
            StubWeatherTool(),
            StubActivityTool(),
        ).run("Istanbul", self.preferences)
        self.evaluation = DeterministicEvaluator().evaluate(
            self.result,
            self.preferences,
        )

    def test_explanation_is_grounded_in_known_activity_names(self) -> None:
        client = FakeStructuredLLMClient(
            [
                {
                    "summary": "Park Walk is the strongest current option.",
                    "weather_context": "The weather is mild and dry.",
                    "recommendation_details": [
                        {
                            "activity_name": "Park Walk",
                            "explanation": (
                                "It matches the requested activity and weather limits."
                            ),
                        }
                    ],
                    "fallback_note": "",
                }
            ]
        )

        explanation = ExplanationService(client).generate(
            self.result,
            self.preferences,
            self.evaluation,
        )

        self.assertIn("Park Walk", explanation.recommendation_details)
        self.assertEqual(
            client.calls[0]["schema_name"],
            "recommendation_explanation",
        )
        prompt_context = json.loads(client.calls[0]["user_prompt"])
        self.assertEqual(
            prompt_context["recommendations"][0]["score"],
            self.result.recommendations[0].score,
        )
        self.assertEqual(
            prompt_context["recommendations"][0]["score_breakdown"],
            {
                "weather_safety": (
                    self.result.recommendations[0]
                    .score_breakdown
                    .weather_safety
                ),
                "preference_match": (
                    self.result.recommendations[0]
                    .score_breakdown
                    .preference_match
                ),
                "comfort_match": (
                    self.result.recommendations[0]
                    .score_breakdown
                    .comfort_match
                ),
                "practicality": (
                    self.result.recommendations[0]
                    .score_breakdown
                    .practicality
                ),
                "total_score": (
                    self.result.recommendations[0]
                    .score_breakdown
                    .total_score
                ),
            },
        )

    def test_explanation_rejects_invented_activity(self) -> None:
        client = FakeStructuredLLMClient(
            [
                {
                    "summary": "A recommendation.",
                    "weather_context": "Weather context.",
                    "recommendation_details": [
                        {
                            "activity_name": "Invented Beach Trip",
                            "explanation": "Not grounded in the agent result.",
                        }
                    ],
                    "fallback_note": "",
                }
            ]
        )

        with self.assertRaisesRegex(LLMServiceError, "invented an activity"):
            ExplanationService(client).generate(
                self.result,
                self.preferences,
                self.evaluation,
            )

    def test_explanation_rejects_missing_recommendation_detail(self) -> None:
        client = FakeStructuredLLMClient(
            [
                {
                    "summary": "A recommendation.",
                    "weather_context": "Weather context.",
                    "recommendation_details": [],
                    "fallback_note": "",
                }
            ]
        )

        with self.assertRaisesRegex(LLMServiceError, "every recommendation"):
            ExplanationService(client).generate(
                self.result,
                self.preferences,
                self.evaluation,
            )

    def test_explanation_rejects_duplicate_recommendation_detail(self) -> None:
        duplicate_detail = {
            "activity_name": "Park Walk",
            "explanation": "It matches the verified result.",
        }
        client = FakeStructuredLLMClient(
            [
                {
                    "summary": "A recommendation.",
                    "weather_context": "Weather context.",
                    "recommendation_details": [
                        duplicate_detail,
                        duplicate_detail,
                    ],
                    "fallback_note": "",
                }
            ]
        )

        with self.assertRaisesRegex(LLMServiceError, "duplicated"):
            ExplanationService(client).generate(
                self.result,
                self.preferences,
                self.evaluation,
            )

    def test_judge_returns_structured_second_opinion(self) -> None:
        client = FakeStructuredLLMClient(
            [
                {
                    "verdict": "approve",
                    "confidence": 0.92,
                    "rationale": "The result is safe, relevant, and explained.",
                    "concerns": [],
                }
            ]
        )

        report = LLMJudgeService(client).evaluate(
            self.result,
            self.preferences,
            self.evaluation,
        )

        self.assertEqual(report.verdict, LLMJudgeVerdict.APPROVE)
        self.assertEqual(report.confidence, 0.92)
        self.assertEqual(client.calls[0]["schema_name"], "llm_judge_report")

    def test_forecast_facts_are_sent_to_both_llm_services(self) -> None:
        self.result.weather.forecast_date = date(2026, 6, 13)
        self.result.weather.minimum_temperature_celsius = 18.8
        self.result.weather.maximum_temperature_celsius = 20.4
        explanation_client = FakeStructuredLLMClient(
            [
                {
                    "summary": "Doğrulanmış öneri özeti.",
                    "weather_context": "13 Haziran hava tahmini.",
                    "recommendation_details": [
                        {
                            "activity_name": "Park Walk",
                            "explanation": "Doğrulanmış açıklama.",
                        }
                    ],
                    "fallback_note": "",
                }
            ]
        )
        judge_client = FakeStructuredLLMClient(
            [
                {
                    "verdict": "approve",
                    "confidence": 0.9,
                    "rationale": "Tahmin bilgileri tutarlı.",
                    "concerns": [],
                }
            ]
        )

        ExplanationService(explanation_client).generate(
            self.result,
            self.preferences,
            self.evaluation,
        )
        LLMJudgeService(judge_client).evaluate(
            self.result,
            self.preferences,
            self.evaluation,
        )

        for client in (explanation_client, judge_client):
            weather_context = json.loads(
                client.calls[0]["user_prompt"]
            )["weather"]
            self.assertEqual(
                weather_context["forecast_date"],
                "2026-06-13",
            )
            self.assertEqual(
                weather_context["minimum_temperature_celsius"],
                18.8,
            )
            self.assertEqual(
                weather_context["maximum_temperature_celsius"],
                20.4,
            )
            self.assertEqual(weather_context["severity_level"], "LOW")

    def test_judge_cannot_approve_deterministic_rejection(self) -> None:
        self.result.recommendations[0].score = 99
        rejected_report = DeterministicEvaluator().evaluate(
            self.result,
            self.preferences,
        )
        client = FakeStructuredLLMClient(
            [
                {
                    "verdict": "approve",
                    "confidence": 0.99,
                    "rationale": "Incorrectly approves an invalid result.",
                    "concerns": [],
                }
            ]
        )

        with self.assertRaisesRegex(
            LLMServiceError,
            "cannot approve",
        ):
            LLMJudgeService(client).evaluate(
                self.result,
                self.preferences,
                rejected_report,
            )

    def test_judge_rejects_invalid_confidence(self) -> None:
        client = FakeStructuredLLMClient(
            [
                {
                    "verdict": "approve",
                    "confidence": 1.5,
                    "rationale": "Invalid confidence.",
                    "concerns": [],
                }
            ]
        )

        with self.assertRaisesRegex(LLMServiceError, "between 0 and 1"):
            LLMJudgeService(client).evaluate(
                self.result,
                self.preferences,
                self.evaluation,
            )


if __name__ == "__main__":
    unittest.main()
