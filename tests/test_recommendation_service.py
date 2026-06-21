"""Tests for the end-to-end recommendation workflow service."""

import os
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.agent.decision_agent import AgentResult, DecisionAgent
from app.config import ConfigurationError
from app.llm.judge_service import LLMJudgeVerdict
from app.models.activity import Activity, CostLevel, TransportEase
from app.models.recommendation import Recommendation
from app.models.recommendation_history import (
    FeedbackValue,
    RecommendationHistoryItem,
    RecommendationHistoryRecord,
)
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from app.models.venue import Venue
from app.services.history_service import RecommendationHistoryRepository
from app.services.recommendation_service import (
    RecommendationService,
    _select_diverse_venues,
)
from app.services.venue_providers import JsonVenueProvider
from app.services.venue_providers.google_places_provider import (
    GooglePlacesVenueProvider,
)
from app.services.venue_service import VenueService
from app.services.venue_service import VenueCatalogError


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
            activity_name = "Park Walk"
            if "Indoor Recovery Run" in user_prompt:
                activity_name = "Indoor Recovery Run"
            return {
                "summary": f"{activity_name} is the best verified option.",
                "weather_context": "The weather was checked.",
                "recommendation_details": [
                    {
                        "activity_name": activity_name,
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
        if schema_name == "llm_activity_candidates":
            return {
                "activities": [
                    {
                        "name": "Indoor Recovery Run",
                        "activity_type": "running",
                        "is_outdoor": False,
                        "min_temperature_celsius": -20,
                        "max_temperature_celsius": 50,
                        "max_precipitation_probability_percent": 100,
                        "max_wind_speed_kmh": 100,
                        "purpose": "cardio exercise",
                        "intensity": "moderate",
                        "duration_minutes": 40,
                        "cost_level": "low",
                        "weather_sensitivity": "none",
                        "requires_reservation": False,
                        "suitable_for": ["solo", "beginners"],
                        "tags": ["running", "indoor", "cardio"],
                    }
                ]
            }
        raise AssertionError(f"Unexpected schema: {schema_name}")


class UnsafeGeneratedActivityLLMClient:
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
        if schema_name == "llm_activity_candidates":
            return {
                "activities": [
                    {
                        "name": "Storm Run",
                        "activity_type": "running",
                        "is_outdoor": True,
                        "min_temperature_celsius": 10,
                        "max_temperature_celsius": 28,
                        "max_precipitation_probability_percent": 20,
                        "max_wind_speed_kmh": 20,
                        "purpose": "cardio exercise",
                        "intensity": "high",
                        "duration_minutes": 45,
                        "cost_level": "free",
                        "weather_sensitivity": "high",
                        "requires_reservation": False,
                        "suitable_for": ["solo"],
                        "tags": ["running", "outdoor"],
                    }
                ]
            }
        if schema_name == "recommendation_explanation":
            return {
                "summary": "Güvenli öneri bulunamadı.",
                "weather_context": "Hava koşulları dış mekan için riskli.",
                "recommendation_details": [],
                "fallback_note": "Üretilen adaylar güvenlik kurallarını geçmedi.",
            }
        if schema_name == "llm_judge_report":
            return {
                "verdict": "approve",
                "confidence": 0.9,
                "rationale": "Güvensiz adaylar öneriye çevrilmemiş.",
                "concerns": [],
            }
        raise AssertionError(f"Unexpected schema: {schema_name}")


class UnrelatedGeneratedActivityLLMClient:
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
        if schema_name == "llm_activity_candidates":
            return {
                "activities": [
                    {
                        "name": "Indoor Movie Night",
                        "activity_type": "culture",
                        "is_outdoor": False,
                        "min_temperature_celsius": -20,
                        "max_temperature_celsius": 50,
                        "max_precipitation_probability_percent": 100,
                        "max_wind_speed_kmh": 100,
                        "purpose": "entertainment",
                        "intensity": "low",
                        "duration_minutes": 120,
                        "cost_level": "medium",
                        "weather_sensitivity": "none",
                        "requires_reservation": False,
                        "suitable_for": ["friends"],
                        "tags": ["culture", "indoor"],
                    }
                ]
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


class StormWeatherTool:
    def get_current_weather(self, _: str) -> WeatherData:
        return WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")

    def get_weather_for_date(
        self,
        _: str,
        target_date: date,
    ) -> WeatherData:
        return WeatherData(
            "Istanbul",
            18,
            90,
            45,
            "Thunderstorm",
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


class EmptyActivityTool:
    def find_candidates(
        self,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> list[Activity]:
        return []

    def find_similar_candidates(
        self,
        activity_type: str,
        is_outdoor: bool | None = None,
        limit: int = 8,
    ) -> list[Activity]:
        return []


class FailingGooglePlacesClient:
    def fetch_nearby_places(self, **_):
        raise VenueCatalogError("Google Places request failed: Quota exceeded")


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
            agent=DecisionAgent(StubWeatherTool(), StubActivityTool()),
            venue_service=VenueService(provider=JsonVenueProvider()),
        )

        result = service.recommend(
            "Istanbul",
            self.preferences,
            venue_origin=(41.0255, 29.0288),
        )

        self.assertTrue(result.deterministic_evaluation.system_behavior_valid)
        self.assertEqual(result.preferences, self.preferences)
        venue = result.agent_result.recommendations[0].venues[0]
        self.assertEqual(venue.name, "Demo Sahil Fotoğraf Noktası")
        self.assertEqual(venue.distance_km, 0.0)
        venue_trace = result.agent_result.recommendations[0].venue_filter_trace
        self.assertTrue(venue_trace)
        self.assertTrue(any(item.passed for item in venue_trace))
        self.assertTrue(any(not item.passed for item in venue_trace))
        self.assertIsNone(result.explanation)
        self.assertIsNone(result.llm_judgment)

    def test_google_places_failure_preserves_safe_activity_recommendation(self) -> None:
        service = RecommendationService(
            agent=DecisionAgent(StubWeatherTool(), StubActivityTool()),
            venue_service=VenueService(
                provider=GooglePlacesVenueProvider(FailingGooglePlacesClient())
            ),
        )

        result = service.recommend(
            "Istanbul",
            self.preferences,
            venue_origin=(41.0, 29.0),
        )

        self.assertEqual(result.agent_result.status, "completed")
        self.assertEqual(
            result.agent_result.recommendations[0].activity.name,
            "Park Walk",
        )
        self.assertEqual(result.agent_result.recommendations[0].venues, [])
        self.assertTrue(result.deterministic_evaluation.system_behavior_valid)

    def test_venue_selection_prefers_unused_places_without_losing_fallback(self) -> None:
        venues = [
            Venue(
                name=f"Venue {index}",
                activity_types=("sports",),
                is_outdoor=False,
                city="Istanbul",
                latitude=41.0,
                longitude=29.0,
                distance_km=float(index),
                transport_ease=TransportEase.EASY,
                cost_level=CostLevel.LOW,
                requires_reservation=False,
                source="google_places",
                provider_venue_id=f"place-{index}",
            )
            for index in range(1, 5)
        ]
        used = {"google_places:place-1", "google_places:place-2"}

        diverse = _select_diverse_venues(venues, used, limit=2)
        fallback = _select_diverse_venues(venues[:2], used, limit=2)

        self.assertEqual(
            [venue.provider_venue_id for venue in diverse],
            ["place-3", "place-4"],
        )
        self.assertEqual(
            [venue.provider_venue_id for venue in fallback],
            ["place-1", "place-2"],
        )

    def test_external_venue_provider_requires_client_configuration(self) -> None:
        previous_value = os.environ.get("VENUE_PROVIDER")
        os.environ["VENUE_PROVIDER"] = "external"
        try:
            with self.assertRaisesRegex(
                ConfigurationError,
                "external venue client",
            ):
                RecommendationService(
                    agent=DecisionAgent(StubWeatherTool(), StubActivityTool())
                )
        finally:
            if previous_value is None:
                del os.environ["VENUE_PROVIDER"]
            else:
                os.environ["VENUE_PROVIDER"] = previous_value

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

    def test_workflow_can_store_recommendation_history(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )
            service = RecommendationService(
                agent=DecisionAgent(StubWeatherTool(), StubActivityTool()),
                history_repository=repository,
                venue_service=VenueService(provider=JsonVenueProvider()),
            )

            result = service.recommend("Istanbul", self.preferences)

            self.assertIsNotNone(result.history_record)
            self.assertEqual(result.history_record.city, "Istanbul")
            self.assertEqual(
                result.history_record.recommendations[0].activity_name,
                "Park Walk",
            )
            self.assertEqual(
                result.history_record.recommendations[0].venue_names,
                ("Demo Sahil Fotoğraf Noktası",),
            )
            self.assertFalse(result.history_record.used_generated_candidates)
            self.assertEqual(
                repository.list_recent()[0].record_id,
                result.history_record.record_id,
            )

    def test_negative_indoor_feedback_adds_small_indoor_penalty(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )
            repository.append(
                _history_record("first", FeedbackValue.NEGATIVE, False)
            )
            repository.append(
                _history_record("second", FeedbackValue.NEGATIVE, False)
            )
            service = RecommendationService(
                agent=DecisionAgent(StubWeatherTool(), StubActivityTool()),
                history_repository=repository,
            )

            result = service.recommend("Istanbul", self.preferences)

            self.assertEqual(result.preferences.indoor_feedback_penalty, 2.0)
            self.assertEqual(
                result.history_record.preferences["indoor_feedback_penalty"],
                2.0,
            )

    def test_llm_generated_activity_is_validated_before_explanation(self) -> None:
        preferences = UserPreferences(
            preferred_activity_type="running",
            prefers_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=28,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        llm_client = FakeStructuredLLMClient()
        service = RecommendationService(
            agent=DecisionAgent(
                StubWeatherTool(),
                EmptyActivityTool(),
            ),
            llm_client=llm_client,
        )

        result = service.recommend("Istanbul", preferences)

        self.assertEqual(result.agent_result.status, "completed")
        self.assertEqual(
            result.agent_result.recommendations[0].activity.name,
            "Indoor Recovery Run",
        )
        self.assertEqual(
            llm_client.schemas,
            [
                "llm_activity_candidates",
                "recommendation_explanation",
                "llm_judge_report",
            ],
        )
        self.assertTrue(
            result.deterministic_evaluation.system_behavior_valid
        )

    def test_unsafe_llm_generated_activity_is_not_recommended(self) -> None:
        preferences = UserPreferences(
            preferred_activity_type="running",
            prefers_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=28,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        llm_client = UnsafeGeneratedActivityLLMClient()
        service = RecommendationService(
            agent=DecisionAgent(
                StormWeatherTool(),
                EmptyActivityTool(),
            ),
            llm_client=llm_client,
        )

        result = service.recommend("Istanbul", preferences)

        self.assertEqual(result.agent_result.status, "no_recommendation")
        self.assertEqual(result.agent_result.recommendations, [])
        self.assertTrue(
            result.deterministic_evaluation.system_behavior_valid
        )
        self.assertIn("llm_activity_candidates", llm_client.schemas)

    def test_unrelated_llm_candidate_keeps_safe_no_recommendation(self) -> None:
        preferences = UserPreferences(
            preferred_activity_type="running",
            prefers_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=28,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        llm_client = UnrelatedGeneratedActivityLLMClient()
        service = RecommendationService(
            agent=DecisionAgent(
                StormWeatherTool(),
                EmptyActivityTool(),
            ),
            llm_client=llm_client,
        )

        result = service.recommend("Istanbul", preferences)

        self.assertEqual(result.agent_result.status, "no_recommendation")
        self.assertEqual(result.agent_result.recommendations, [])
        self.assertIsNone(result.explanation)
        self.assertIsNone(result.llm_judgment)
        self.assertEqual(llm_client.schemas, ["llm_activity_candidates"])

def _history_record(
    record_id: str,
    feedback: FeedbackValue,
    is_outdoor: bool,
) -> RecommendationHistoryRecord:
    return RecommendationHistoryRecord(
        record_id=record_id,
        created_at="2026-06-19T10:00:00+00:00",
        city="Istanbul",
        target_date=None,
        status="completed",
        used_safe_fallback=not is_outdoor,
        used_generated_candidates=False,
        weather={"city": "Istanbul", "severity_level": "LOW"},
        preferences={"preferred_activity_type": "walking"},
        recommendations=[
            RecommendationHistoryItem(
                activity_name="Indoor Track Walk",
                activity_type="walking",
                is_outdoor=is_outdoor,
                score=90.0,
            )
        ],
        feedback=feedback,
    )


if __name__ == "__main__":
    unittest.main()
