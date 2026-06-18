"""Independent deterministic evaluation of recommendation agent results."""

from dataclasses import dataclass
from enum import Enum

from app.agent.decision_agent import AgentResult
from app.agent.planner import AgentAction
from app.core.rules import evaluate_activity
from app.core.scoring import score_activity
from app.models.user_preferences import UserPreferences


class EvaluationVerdict(str, Enum):
    """Terminal judgment produced by the evaluator."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NO_RECOMMENDATION = "no_recommendation"


@dataclass(frozen=True)
class EvaluationCheck:
    """Result of one independently evaluated quality requirement."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvaluationReport:
    """Structured evaluation report for one agent run."""

    verdict: EvaluationVerdict
    system_behavior_valid: bool
    recommendation_success: bool
    quality_score: float
    checks: list[EvaluationCheck]

    @property
    def failed_checks(self) -> list[EvaluationCheck]:
        """Return only failed quality checks."""
        return [check for check in self.checks if not check.passed]


class DeterministicEvaluator:
    """Verify safety, consistency, explainability, and fallback behavior."""

    def __init__(self, minimum_recommendation_score: float = 45.0) -> None:
        self.minimum_recommendation_score = minimum_recommendation_score

    def evaluate(
        self,
        result: AgentResult,
        preferences: UserPreferences,
    ) -> EvaluationReport:
        """Evaluate an agent result without trusting its generated fields."""
        checks = [
            self._check_result_contract(result),
            self._check_trace(result),
            self._check_safety(result, preferences),
            self._check_score_integrity(result, preferences),
            self._check_explanations(result),
            self._check_fallback_consistency(result),
        ]
        system_behavior_valid = all(check.passed for check in checks)
        recommendation_success = (
            system_behavior_valid
            and result.status == "completed"
            and bool(result.recommendations)
        )

        if not system_behavior_valid:
            verdict = EvaluationVerdict.REJECTED
        elif recommendation_success:
            verdict = EvaluationVerdict.APPROVED
        else:
            verdict = EvaluationVerdict.NO_RECOMMENDATION

        passed_count = sum(check.passed for check in checks)
        quality_score = round((passed_count / len(checks)) * 100, 2)

        return EvaluationReport(
            verdict=verdict,
            system_behavior_valid=system_behavior_valid,
            recommendation_success=recommendation_success,
            quality_score=quality_score,
            checks=checks,
        )

    @staticmethod
    def _check_result_contract(result: AgentResult) -> EvaluationCheck:
        completed_is_consistent = (
            result.status == "completed" and bool(result.recommendations)
        )
        no_result_is_consistent = (
            result.status == "no_recommendation" and not result.recommendations
        )
        passed = completed_is_consistent or no_result_is_consistent

        return EvaluationCheck(
            name="result_contract",
            passed=passed,
            detail=(
                "Status and recommendation payload are consistent."
                if passed
                else "Status and recommendation payload contradict each other."
            ),
        )

    @staticmethod
    def _check_trace(result: AgentResult) -> EvaluationCheck:
        actions = [step.action for step in result.trace]
        has_required_start = bool(actions) and actions[0] is AgentAction.FETCH_WEATHER
        has_scoring = AgentAction.SCORE_CANDIDATES in actions

        if result.status == "completed":
            has_expected_end = bool(actions) and actions[-1] is AgentAction.FINALIZE
        elif result.status == "no_recommendation":
            has_expected_end = (
                bool(actions) and actions[-1] is AgentAction.STOP_NO_RESULT
            )
        else:
            has_expected_end = False

        passed = has_required_start and has_scoring and has_expected_end
        return EvaluationCheck(
            name="decision_trace",
            passed=passed,
            detail=(
                "Decision trace contains weather retrieval, scoring, and a valid end."
                if passed
                else "Decision trace is missing required actions or terminal state."
            ),
        )

    @staticmethod
    def _check_safety(
        result: AgentResult,
        preferences: UserPreferences,
    ) -> EvaluationCheck:
        unsafe_recommendations: list[str] = []

        for recommendation in result.recommendations:
            rule_result = evaluate_activity(
                result.weather,
                preferences,
                recommendation.activity,
            )
            warnings_match = set(recommendation.warnings) == set(
                rule_result.warnings
            )
            if not rule_result.is_eligible or not warnings_match:
                unsafe_recommendations.append(recommendation.activity.name)

        passed = not unsafe_recommendations
        return EvaluationCheck(
            name="safety_and_warning_integrity",
            passed=passed,
            detail=(
                "All recommendations independently passed safety rules."
                if passed
                else "Unsafe or warning-inconsistent recommendations: "
                + ", ".join(unsafe_recommendations)
            ),
        )

    def _check_score_integrity(
        self,
        result: AgentResult,
        preferences: UserPreferences,
    ) -> EvaluationCheck:
        invalid_scores: list[str] = []
        scores = [recommendation.score for recommendation in result.recommendations]

        for recommendation in result.recommendations:
            recalculated = score_activity(
                result.weather,
                preferences,
                recommendation.activity,
            )
            score_matches = abs(recommendation.score - recalculated.total_score) <= 0.01
            score_is_sufficient = (
                0 <= recommendation.score <= 100
                and recommendation.score >= self.minimum_recommendation_score
            )
            if not score_matches or not score_is_sufficient:
                invalid_scores.append(recommendation.activity.name)

        is_ranked = scores == sorted(scores, reverse=True)
        passed = not invalid_scores and is_ranked
        return EvaluationCheck(
            name="score_integrity",
            passed=passed,
            detail=(
                "Scores match independent recalculation and ranking order."
                if passed
                else "Invalid, weak, altered, or unsorted scores: "
                + (", ".join(invalid_scores) or "ranking order")
            ),
        )

    @staticmethod
    def _check_explanations(result: AgentResult) -> EvaluationCheck:
        incomplete = [
            recommendation.activity.name
            for recommendation in result.recommendations
            if len(
                [
                    component
                    for component in recommendation.reasoning.split(";")
                    if component.strip()
                ]
            )
            < 5
        ]
        passed = not incomplete
        return EvaluationCheck(
            name="explanation_completeness",
            passed=passed,
            detail=(
                "Every recommendation explains all scoring components."
                if passed
                else "Incomplete explanations: " + ", ".join(incomplete)
            ),
        )

    @staticmethod
    def _check_fallback_consistency(result: AgentResult) -> EvaluationCheck:
        actions = [step.action for step in result.trace]
        trace_used_fallback = any(
            action
            in {
                AgentAction.LOAD_RELATED_ALTERNATIVES,
                AgentAction.LOAD_SAFE_ALTERNATIVES,
            }
            for action in actions
        )
        recommendations_are_indoor = all(
            not recommendation.activity.is_outdoor
            for recommendation in result.recommendations
        )

        if result.used_safe_fallback:
            passed = trace_used_fallback and recommendations_are_indoor
        else:
            passed = not trace_used_fallback

        return EvaluationCheck(
            name="fallback_consistency",
            passed=passed,
            detail=(
                "Fallback flag, trace, and recommendations are consistent."
                if passed
                else "Fallback metadata contradicts the decision trace or activities."
            ),
        )
