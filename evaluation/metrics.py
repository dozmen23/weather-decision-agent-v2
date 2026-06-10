"""Metrics and report models for batch agent evaluation."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScenarioEvaluation:
    """Expected-versus-actual result for one evaluation scenario."""

    case_id: str
    description: str
    passed: bool
    actual_status: str
    actual_top_activity: str | None
    used_safe_fallback: bool
    evaluator_verdict: str
    system_behavior_valid: bool
    recommendation_success: bool
    quality_score: float
    mismatches: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationSummary:
    """Aggregate metrics across a complete evaluation data set."""

    total_cases: int
    passed_cases: int
    scenario_pass_rate_percent: float
    system_validity_rate_percent: float
    recommendation_success_rate_percent: float
    evaluator_approval_rate_percent: float
    average_quality_score: float


@dataclass(frozen=True)
class BatchEvaluationReport:
    """Complete batch report with scenario details and aggregate metrics."""

    scenarios: list[ScenarioEvaluation]
    summary: EvaluationSummary


def build_summary(scenarios: list[ScenarioEvaluation]) -> EvaluationSummary:
    """Calculate aggregate metrics from evaluated scenarios."""
    total_cases = len(scenarios)
    if total_cases == 0:
        return EvaluationSummary(
            total_cases=0,
            passed_cases=0,
            scenario_pass_rate_percent=0.0,
            system_validity_rate_percent=0.0,
            recommendation_success_rate_percent=0.0,
            evaluator_approval_rate_percent=0.0,
            average_quality_score=0.0,
        )

    passed_cases = sum(scenario.passed for scenario in scenarios)
    system_valid_cases = sum(
        scenario.system_behavior_valid for scenario in scenarios
    )
    recommendation_successes = sum(
        scenario.recommendation_success for scenario in scenarios
    )
    approved_cases = sum(
        scenario.evaluator_verdict == "approved" for scenario in scenarios
    )
    average_quality = sum(
        scenario.quality_score for scenario in scenarios
    ) / total_cases

    return EvaluationSummary(
        total_cases=total_cases,
        passed_cases=passed_cases,
        scenario_pass_rate_percent=_percentage(passed_cases, total_cases),
        system_validity_rate_percent=_percentage(
            system_valid_cases,
            total_cases,
        ),
        recommendation_success_rate_percent=_percentage(
            recommendation_successes,
            total_cases,
        ),
        evaluator_approval_rate_percent=_percentage(
            approved_cases,
            total_cases,
        ),
        average_quality_score=round(average_quality, 2),
    )


def _percentage(value: int, total: int) -> float:
    return round((value / total) * 100, 2)
