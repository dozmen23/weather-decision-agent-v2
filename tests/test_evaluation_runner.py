"""Tests for batch scenario evaluation and aggregate metrics."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from evaluation.evaluation_runner import (
    EvaluationDataError,
    EvaluationRunner,
)
from app.services.venue_providers.google_places_provider import (
    GooglePlacesVenueProvider,
)


class FakeGooglePlacesClient:
    def __init__(self, places):
        self.places = places

    def fetch_nearby_places(self, **_):
        return self.places


class EvaluationRunnerTests(unittest.TestCase):
    def test_default_scenarios_all_pass(self) -> None:
        report = EvaluationRunner().run()

        self.assertEqual(report.summary.total_cases, 13)
        self.assertEqual(report.summary.passed_cases, 13)
        self.assertEqual(report.summary.scenario_pass_rate_percent, 100.0)
        self.assertEqual(report.summary.system_validity_rate_percent, 100.0)
        self.assertEqual(
            report.summary.recommendation_success_rate_percent,
            92.31,
        )
        self.assertEqual(report.summary.evaluator_approval_rate_percent, 92.31)
        venue_case = next(
            scenario
            for scenario in report.scenarios
            if scenario.case_id == "coordinate-origin-sorts-venue-candidates"
        )
        self.assertTrue(venue_case.passed)

    def test_inline_catalog_can_exercise_no_recommendation_path(self) -> None:
        case = self._base_case()
        case["id"] = "inline-no-result"
        case["weather"] = {
            "city": "Istanbul",
            "temperature_celsius": -8,
            "precipitation_probability_percent": 90,
            "wind_speed_kmh": 55,
            "condition": "Thunderstorm",
        }
        case["preferences"] = {
            "preferred_activity_type": "running",
            "prefers_outdoor": True,
            "min_temperature_celsius": 5,
            "max_temperature_celsius": 25,
            "max_precipitation_probability_percent": 30,
            "max_wind_speed_kmh": 20,
        }
        case["activities"] = [
            {
                "name": "Unsafe Run",
                "activity_type": "running",
                "is_outdoor": True,
                "min_temperature_celsius": 10,
                "max_temperature_celsius": 28,
                "max_precipitation_probability_percent": 20,
                "max_wind_speed_kmh": 20,
            }
        ]
        case["expected"] = {
            "status": "no_recommendation",
            "top_activity": None,
            "used_safe_fallback": True,
            "verdict": "no_recommendation",
            "required_actions": ["load_safe_alternatives", "stop_no_result"],
        }

        report = self._run_temporary_cases([case])

        self.assertEqual(report.summary.passed_cases, 1)
        self.assertEqual(report.scenarios[0].actual_top_activity, None)

    def test_wrong_expectation_is_reported_as_scenario_failure(self) -> None:
        case = self._base_case()
        case["expected"]["top_activity"] = "Wrong Activity"

        report = self._run_temporary_cases([case])

        self.assertEqual(report.summary.passed_cases, 0)
        self.assertIn(
            "top_activity",
            report.scenarios[0].mismatches[0],
        )

    def test_empty_data_set_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvaluationDataError, "cannot be empty"):
            self._run_temporary_cases([])

    def test_missing_case_field_is_rejected(self) -> None:
        invalid_case = self._base_case()
        del invalid_case["expected"]

        with self.assertRaisesRegex(EvaluationDataError, "missing: expected"):
            self._run_temporary_cases([invalid_case])

    def test_invalid_venue_origin_is_rejected(self) -> None:
        invalid_case = self._base_case()
        invalid_case["venue_origin"] = {"latitude": 120, "longitude": 29}

        with self.assertRaisesRegex(EvaluationDataError, "invalid venue origin"):
            self._run_temporary_cases([invalid_case])

    def test_runner_ignores_runtime_venue_provider_environment(self) -> None:
        previous_value = os.environ.get("VENUE_PROVIDER")
        os.environ["VENUE_PROVIDER"] = "external"
        try:
            report = self._run_temporary_cases([self._base_case()])
        finally:
            if previous_value is None:
                del os.environ["VENUE_PROVIDER"]
            else:
                os.environ["VENUE_PROVIDER"] = previous_value

        self.assertEqual(report.summary.passed_cases, 1)

    def test_google_places_fixture_verifies_source_sorting_and_filtering(self) -> None:
        case = self._base_case()
        case["id"] = "google-places-indoor-walk"
        case["venue_origin"] = {"latitude": 41.0, "longitude": 29.0}
        case["preferences"]["prefers_outdoor"] = False
        case["preferences"]["max_cost_level"] = "low"
        case["expected"].update(
            {
                "top_activity": "Indoor Track Walk",
                "top_venue": "Yakın Uygun AVM",
                "top_venue_source": "google_places",
                "venue_count": 1,
                "venue_trace_has_rejection_reason": "Bütçe sınırını aştı.",
            }
        )
        provider = GooglePlacesVenueProvider(
            FakeGooglePlacesClient(
                [
                    {
                        "id": "expensive",
                        "displayName": {"text": "Pahalı AVM"},
                        "location": {"latitude": 41.0002, "longitude": 29.0},
                        "types": ["shopping_mall"],
                        "priceLevel": "PRICE_LEVEL_EXPENSIVE",
                        "businessStatus": "OPERATIONAL",
                    },
                    {
                        "id": "affordable",
                        "displayName": {"text": "Yakın Uygun AVM"},
                        "location": {"latitude": 41.0008, "longitude": 29.0},
                        "types": ["shopping_mall"],
                        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
                        "businessStatus": "OPERATIONAL",
                    },
                ]
            )
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "cases.json"
            path.write_text(
                json.dumps({"version": 1, "cases": [case]}),
                encoding="utf-8",
            )
            report = EvaluationRunner(path, venue_provider=provider).run()

        self.assertEqual(report.summary.passed_cases, 1)

    def _run_temporary_cases(self, cases: list[dict[str, object]]):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "cases.json"
            path.write_text(
                json.dumps({"version": 1, "cases": cases}),
                encoding="utf-8",
            )
            return EvaluationRunner(path).run()

    @staticmethod
    def _base_case() -> dict[str, object]:
        return {
            "id": "test-case",
            "description": "A valid walking scenario.",
            "city": "Istanbul",
            "weather": {
                "city": "Istanbul",
                "temperature_celsius": 22.5,
                "precipitation_probability_percent": 5,
                "wind_speed_kmh": 5,
                "condition": "Clear sky",
            },
            "preferences": {
                "preferred_activity_type": "walking",
                "prefers_outdoor": True,
                "min_temperature_celsius": 15,
                "max_temperature_celsius": 30,
                "max_precipitation_probability_percent": 40,
                "max_wind_speed_kmh": 25,
            },
            "expected": {
                "status": "completed",
                "top_activity": "Park Walk",
                "used_safe_fallback": False,
                "verdict": "approved",
                "required_actions": ["load_preferred_candidates"],
            },
        }


if __name__ == "__main__":
    unittest.main()
