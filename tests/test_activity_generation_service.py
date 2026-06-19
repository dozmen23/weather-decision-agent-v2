"""Tests for controlled LLM-assisted activity generation."""

import unittest
from typing import Any

from app.llm.activity_generation_service import ActivityGenerationService
from app.llm.client import LLMServiceError
from app.models.activity import CostLevel
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


class FakeStructuredLLMClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.schema_name: str | None = None

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.schema_name = schema_name
        return self.payload


class ActivityGenerationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weather = WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")
        self.preferences = UserPreferences(
            preferred_activity_type="running",
            prefers_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=28,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )

    def test_generated_activity_is_parsed_into_domain_model(self) -> None:
        client = FakeStructuredLLMClient(
            {
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
        )

        activities = ActivityGenerationService(client).generate(
            self.weather,
            self.preferences,
        )

        self.assertEqual(client.schema_name, "llm_activity_candidates")
        self.assertEqual(activities[0].name, "Indoor Recovery Run")
        self.assertIs(activities[0].cost_level, CostLevel.LOW)
        self.assertFalse(activities[0].is_outdoor)

    def test_duplicate_generated_activity_names_are_rejected(self) -> None:
        duplicate = {
            "name": "Indoor Run",
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
            "suitable_for": ["solo"],
            "tags": ["running"],
        }
        client = FakeStructuredLLMClient(
            {"activities": [duplicate, {**duplicate, "name": " indoor run "}]}
        )

        with self.assertRaisesRegex(LLMServiceError, "duplicate"):
            ActivityGenerationService(client).generate(
                self.weather,
                self.preferences,
            )

    def test_unrelated_generated_activity_is_rejected(self) -> None:
        client = FakeStructuredLLMClient(
            {
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
        )

        with self.assertRaisesRegex(LLMServiceError, "unrelated"):
            ActivityGenerationService(client).generate(
                self.weather,
                self.preferences,
            )


if __name__ == "__main__":
    unittest.main()
