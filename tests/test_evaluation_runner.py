"""Tests for batch scenario evaluation and aggregate metrics."""

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.evaluation_runner import (
    EvaluationDataError,
    EvaluationRunner,
)


class EvaluationRunnerTests(unittest.TestCase):
    def test_default_scenarios_all_pass(self) -> None:
        report = EvaluationRunner().run()

        self.assertEqual(report.summary.total_cases, 8)
        self.assertEqual(report.summary.passed_cases, 8)
        self.assertEqual(report.summary.scenario_pass_rate_percent, 100.0)
        self.assertEqual(report.summary.system_validity_rate_percent, 100.0)
        self.assertEqual(
            report.summary.recommendation_success_rate_percent,
            100.0,
        )
        self.assertEqual(report.summary.evaluator_approval_rate_percent, 100.0)

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
