"""Use an LLM as a structured second opinion after deterministic evaluation."""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.agent.decision_agent import AgentResult
from app.llm.client import LLMServiceError, StructuredLLMClient
from app.models.user_preferences import UserPreferences
from evaluation.evaluator import EvaluationReport


JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["approve", "reject", "needs_review"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "rationale": {"type": "string"},
        "concerns": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["verdict", "confidence", "rationale", "concerns"],
    "additionalProperties": False,
}


class LLMJudgeVerdict(str, Enum):
    """Possible verdicts from the LLM second-opinion judge."""

    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class LLMJudgeReport:
    """Structured second-opinion judgment."""

    verdict: LLMJudgeVerdict
    confidence: float
    rationale: str
    concerns: list[str]


class LLMJudgeService:
    """Ask an LLM to review a deterministic evaluation report."""

    def __init__(self, client: StructuredLLMClient) -> None:
        self.client = client

    def evaluate(
        self,
        result: AgentResult,
        preferences: UserPreferences,
        deterministic_report: EvaluationReport,
    ) -> LLMJudgeReport:
        """Return a structured second opinion without overriding hard rules."""
        payload = self.client.generate_structured(
            system_prompt=(
                "You are a second-opinion evaluator for a weather activity agent. "
                "The deterministic evaluator and safety rules are authoritative. "
                "Never approve a result when system_behavior_valid is false. "
                "Review clarity, relevance, and whether the recommendation follows "
                "the supplied facts. Return only the requested structured fields. "
                "Write rationale and concerns in Turkish."
            ),
            user_prompt=json.dumps(
                _build_judge_context(
                    result,
                    preferences,
                    deterministic_report,
                ),
                ensure_ascii=True,
                sort_keys=True,
            ),
            schema_name="llm_judge_report",
            json_schema=JUDGE_SCHEMA,
        )
        report = _parse_judge_report(payload)

        if (
            not deterministic_report.system_behavior_valid
            and report.verdict is LLMJudgeVerdict.APPROVE
        ):
            raise LLMServiceError(
                "LLM judge cannot approve a deterministically invalid result."
            )

        return report


def _build_judge_context(
    result: AgentResult,
    preferences: UserPreferences,
    deterministic_report: EvaluationReport,
) -> dict[str, Any]:
    return {
        "agent_status": result.status,
        "weather": {
            "city": result.weather.city,
            "forecast_date": (
                result.weather.forecast_date.isoformat()
                if result.weather.forecast_date
                else None
            ),
            "temperature_celsius": result.weather.temperature_celsius,
            "minimum_temperature_celsius": (
                result.weather.minimum_temperature_celsius
            ),
            "maximum_temperature_celsius": (
                result.weather.maximum_temperature_celsius
            ),
            "precipitation_probability_percent": (
                result.weather.precipitation_probability_percent
            ),
            "wind_speed_kmh": result.weather.wind_speed_kmh,
            "condition": result.weather.condition,
            "severity_level": result.weather.severity_level.value,
        },
        "preferences": {
            "preferred_activity_type": preferences.preferred_activity_type,
            "prefers_outdoor": preferences.prefers_outdoor,
            "max_cost_level": preferences.max_cost_level.value,
            "max_duration_minutes": preferences.max_duration_minutes,
            "preferred_intensity": (
                preferences.preferred_intensity.value
                if preferences.preferred_intensity
                else None
            ),
            "avoid_reservations": preferences.avoid_reservations,
            "suitable_for": preferences.suitable_for,
            "max_transport_ease": preferences.max_transport_ease.value,
            "indoor_feedback_penalty": preferences.indoor_feedback_penalty,
        },
        "recommendations": [
            {
                "activity_name": recommendation.activity.name,
                "score": recommendation.score,
                "score_breakdown": {
                    "weather_safety": (
                        recommendation.score_breakdown.weather_safety
                    ),
                    "preference_match": (
                        recommendation.score_breakdown.preference_match
                    ),
                    "comfort_match": (
                        recommendation.score_breakdown.comfort_match
                    ),
                    "practicality": recommendation.score_breakdown.practicality,
                    "total_score": recommendation.score_breakdown.total_score,
                },
                "reasoning": recommendation.reasoning,
                "warnings": recommendation.warnings,
                "venues": [
                    {
                        "name": venue.name,
                        "distance_km": venue.distance_km,
                        "transport_ease": venue.transport_ease.value,
                        "cost_level": venue.cost_level.value,
                        "requires_reservation": venue.requires_reservation,
                        "source": venue.source,
                    }
                    for venue in recommendation.venues
                ],
            }
            for recommendation in result.recommendations
        ],
        "used_safe_fallback": result.used_safe_fallback,
        "decision_trace": [
            step.action.value for step in result.trace
        ],
        "deterministic_evaluation": {
            "verdict": deterministic_report.verdict.value,
            "system_behavior_valid": (
                deterministic_report.system_behavior_valid
            ),
            "recommendation_success": (
                deterministic_report.recommendation_success
            ),
            "quality_score": deterministic_report.quality_score,
            "failed_checks": [
                {
                    "name": check.name,
                    "detail": check.detail,
                }
                for check in deterministic_report.failed_checks
            ],
        },
    }


def _parse_judge_report(payload: dict[str, Any]) -> LLMJudgeReport:
    try:
        verdict = LLMJudgeVerdict(payload["verdict"])
        confidence = float(payload["confidence"])
        rationale = payload["rationale"]
        concerns = payload["concerns"]
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMServiceError(
            "LLM judge returned an invalid structured report."
        ) from exc

    if not 0 <= confidence <= 1:
        raise LLMServiceError(
            "LLM judge confidence must be between 0 and 1."
        )
    if not isinstance(rationale, str) or not rationale.strip():
        raise LLMServiceError("LLM judge rationale cannot be empty.")
    if (
        not isinstance(concerns, list)
        or not all(
            isinstance(concern, str) and concern.strip()
            for concern in concerns
        )
    ):
        raise LLMServiceError(
            "LLM judge concerns must be a list of non-empty strings."
        )

    return LLMJudgeReport(
        verdict=verdict,
        confidence=confidence,
        rationale=rationale.strip(),
        concerns=[concern.strip() for concern in concerns],
    )
