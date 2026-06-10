"""Run reproducible agent evaluations from a JSON scenario data set."""

import json
from pathlib import Path
from typing import Any

from app.agent.decision_agent import DecisionAgent
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from app.services.activity_service import ActivityService
from evaluation.evaluator import DeterministicEvaluator
from evaluation.metrics import (
    BatchEvaluationReport,
    ScenarioEvaluation,
    build_summary,
)


DEFAULT_CASES_PATH = Path(__file__).with_name("test_cases.json")


class EvaluationDataError(ValueError):
    """Raised when the evaluation data set is missing or malformed."""


class StaticWeatherTool:
    """Return scenario weather without making a network request."""

    def __init__(self, weather: WeatherData) -> None:
        self.weather = weather

    def get_current_weather(self, _: str) -> WeatherData:
        return self.weather


class EvaluationRunner:
    """Execute the real decision agent against reproducible scenarios."""

    def __init__(
        self,
        cases_path: Path = DEFAULT_CASES_PATH,
        evaluator: DeterministicEvaluator | None = None,
    ) -> None:
        self.cases_path = cases_path
        self.evaluator = evaluator or DeterministicEvaluator()

    def run(self) -> BatchEvaluationReport:
        """Run every case and return detailed and aggregate results."""
        scenarios = [
            self._run_case(case) for case in self._load_cases()
        ]
        return BatchEvaluationReport(
            scenarios=scenarios,
            summary=build_summary(scenarios),
        )

    def _run_case(self, case: dict[str, Any]) -> ScenarioEvaluation:
        weather = _parse_weather(case["weather"], case["id"])
        preferences = _parse_preferences(case["preferences"], case["id"])
        expected = case["expected"]

        result = DecisionAgent(
            weather_tool=StaticWeatherTool(weather),
            activity_tool=ActivityService(),
        ).run(case["city"], preferences)
        evaluation = self.evaluator.evaluate(result, preferences)

        actual_top_activity = (
            result.recommendations[0].activity.name
            if result.recommendations
            else None
        )
        actual_actions = {step.action.value for step in result.trace}
        mismatches: list[str] = []

        _compare(
            mismatches,
            "status",
            expected["status"],
            result.status,
        )
        _compare(
            mismatches,
            "top_activity",
            expected.get("top_activity"),
            actual_top_activity,
        )
        _compare(
            mismatches,
            "used_safe_fallback",
            expected["used_safe_fallback"],
            result.used_safe_fallback,
        )
        _compare(
            mismatches,
            "verdict",
            expected["verdict"],
            evaluation.verdict.value,
        )

        for required_action in expected.get("required_actions", []):
            if required_action not in actual_actions:
                mismatches.append(
                    f"missing required action: {required_action}"
                )

        return ScenarioEvaluation(
            case_id=case["id"],
            description=case["description"],
            passed=not mismatches,
            actual_status=result.status,
            actual_top_activity=actual_top_activity,
            used_safe_fallback=result.used_safe_fallback,
            evaluator_verdict=evaluation.verdict.value,
            system_behavior_valid=evaluation.system_behavior_valid,
            recommendation_success=evaluation.recommendation_success,
            quality_score=evaluation.quality_score,
            mismatches=mismatches,
        )

    def _load_cases(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EvaluationDataError(
                f"Evaluation data set was not found: {self.cases_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise EvaluationDataError(
                f"Evaluation data set contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(payload, dict) or not isinstance(
            payload.get("cases"),
            list,
        ):
            raise EvaluationDataError(
                "Evaluation data set must contain a 'cases' list."
            )

        cases = payload["cases"]
        if not cases:
            raise EvaluationDataError("Evaluation data set cannot be empty.")

        for index, case in enumerate(cases):
            _validate_case(case, index)

        return cases


def _validate_case(case: Any, index: int) -> None:
    if not isinstance(case, dict):
        raise EvaluationDataError(
            f"Evaluation case at index {index} must be an object."
        )

    required_fields = {
        "id",
        "description",
        "city",
        "weather",
        "preferences",
        "expected",
    }
    missing = required_fields - case.keys()
    if missing:
        raise EvaluationDataError(
            f"Evaluation case at index {index} is missing: "
            + ", ".join(sorted(missing))
        )

    if not isinstance(case["weather"], dict):
        raise EvaluationDataError(
            f"Evaluation case '{case['id']}' has invalid weather data."
        )
    if not isinstance(case["preferences"], dict):
        raise EvaluationDataError(
            f"Evaluation case '{case['id']}' has invalid preferences."
        )
    if not isinstance(case["expected"], dict):
        raise EvaluationDataError(
            f"Evaluation case '{case['id']}' has invalid expectations."
        )


def _parse_weather(raw: dict[str, Any], case_id: str) -> WeatherData:
    try:
        return WeatherData(
            city=str(raw["city"]),
            temperature_celsius=float(raw["temperature_celsius"]),
            precipitation_probability_percent=int(
                raw["precipitation_probability_percent"]
            ),
            wind_speed_kmh=float(raw["wind_speed_kmh"]),
            condition=str(raw["condition"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluationDataError(
            f"Evaluation case '{case_id}' has incomplete weather data."
        ) from exc


def _parse_preferences(
    raw: dict[str, Any],
    case_id: str,
) -> UserPreferences:
    try:
        return UserPreferences(
            preferred_activity_type=str(raw["preferred_activity_type"]),
            prefers_outdoor=_require_boolean(
                raw["prefers_outdoor"],
                case_id,
            ),
            min_temperature_celsius=float(
                raw["min_temperature_celsius"]
            ),
            max_temperature_celsius=float(
                raw["max_temperature_celsius"]
            ),
            max_precipitation_probability_percent=int(
                raw["max_precipitation_probability_percent"]
            ),
            max_wind_speed_kmh=float(raw["max_wind_speed_kmh"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluationDataError(
            f"Evaluation case '{case_id}' has incomplete preferences."
        ) from exc


def _require_boolean(value: Any, case_id: str) -> bool:
    if not isinstance(value, bool):
        raise EvaluationDataError(
            f"Evaluation case '{case_id}' has a non-boolean preference."
        )
    return value


def _compare(
    mismatches: list[str],
    field_name: str,
    expected: Any,
    actual: Any,
) -> None:
    if expected != actual:
        mismatches.append(
            f"{field_name}: expected {expected!r}, got {actual!r}"
        )


def _print_report(report: BatchEvaluationReport) -> None:
    for scenario in report.scenarios:
        marker = "PASS" if scenario.passed else "FAIL"
        print(
            f"[{marker}] {scenario.case_id}: "
            f"{scenario.actual_top_activity or 'no recommendation'}"
        )
        for mismatch in scenario.mismatches:
            print(f"  - {mismatch}")

    summary = report.summary
    print("\nSummary")
    print(f"Cases: {summary.passed_cases}/{summary.total_cases}")
    print(f"Scenario pass rate: {summary.scenario_pass_rate_percent}%")
    print(f"System validity rate: {summary.system_validity_rate_percent}%")
    print(
        "Recommendation success rate: "
        f"{summary.recommendation_success_rate_percent}%"
    )
    print(
        "Evaluator approval rate: "
        f"{summary.evaluator_approval_rate_percent}%"
    )
    print(f"Average quality score: {summary.average_quality_score}")


if __name__ == "__main__":
    _print_report(EvaluationRunner().run())
