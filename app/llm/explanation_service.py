"""Generate user-facing explanations without changing decision facts."""

import json
from dataclasses import dataclass
from typing import Any

from app.agent.decision_agent import AgentResult
from app.llm.client import LLMServiceError, StructuredLLMClient
from app.models.user_preferences import UserPreferences
from evaluation.evaluator import EvaluationReport


EXPLANATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "weather_context": {"type": "string"},
        "recommendation_details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "activity_name": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["activity_name", "explanation"],
                "additionalProperties": False,
            },
        },
        "fallback_note": {"type": "string"},
    },
    "required": [
        "summary",
        "weather_context",
        "recommendation_details",
        "fallback_note",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class RecommendationExplanation:
    """Natural-language explanation generated from verified system facts."""

    summary: str
    weather_context: str
    recommendation_details: dict[str, str]
    fallback_note: str


class ExplanationService:
    """Ask an LLM to explain, but never recalculate, agent decisions."""

    def __init__(self, client: StructuredLLMClient) -> None:
        self.client = client

    def generate(
        self,
        result: AgentResult,
        preferences: UserPreferences,
        evaluation: EvaluationReport,
    ) -> RecommendationExplanation:
        """Generate an explanation grounded in deterministic agent output."""
        payload = self.client.generate_structured(
            system_prompt=(
                "You explain a weather recommendation system's verified output. "
                "Treat weather values, scores, warnings, evaluator checks, and "
                "activity names as immutable facts. Do not invent activities, "
                "change scores, or claim that an unsafe result is safe. Write for "
                "an everyday end user in warm, natural Turkish. Avoid technical "
                "phrases such as deterministic, evaluator, score breakdown, total "
                "score, component, trace, or rule engine. Do not list numeric score "
                "components. Explain briefly why the recommendation feels sensible "
                "for the weather and preference."
            ),
            user_prompt=json.dumps(
                _build_explanation_context(result, preferences, evaluation),
                ensure_ascii=True,
                sort_keys=True,
            ),
            schema_name="recommendation_explanation",
            json_schema=EXPLANATION_SCHEMA,
        )
        return _parse_explanation(payload, result)


def _build_explanation_context(
    result: AgentResult,
    preferences: UserPreferences,
    evaluation: EvaluationReport,
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
                "deterministic_reasoning": recommendation.reasoning,
                "warnings": recommendation.warnings,
            }
            for recommendation in result.recommendations
        ],
        "used_safe_fallback": result.used_safe_fallback,
        "evaluator": {
            "verdict": evaluation.verdict.value,
            "quality_score": evaluation.quality_score,
            "failed_checks": [
                check.name for check in evaluation.failed_checks
            ],
        },
    }


def _parse_explanation(
    payload: dict[str, Any],
    result: AgentResult,
) -> RecommendationExplanation:
    try:
        summary = _require_text(payload["summary"], "summary")
        weather_context = _require_text(
            payload["weather_context"],
            "weather_context",
        )
        fallback_note = _require_text(
            payload["fallback_note"],
            "fallback_note",
            allow_empty=True,
        )
        raw_details = payload["recommendation_details"]
    except (KeyError, TypeError) as exc:
        raise LLMServiceError(
            "LLM explanation is missing required fields."
        ) from exc

    if not isinstance(raw_details, list):
        raise LLMServiceError(
            "LLM explanation details must be a list."
        )

    expected_names = {
        recommendation.activity.name for recommendation in result.recommendations
    }
    details: dict[str, str] = {}

    for item in raw_details:
        if not isinstance(item, dict):
            raise LLMServiceError(
                "LLM explanation contains an invalid detail item."
            )
        try:
            activity_name = _require_text(
                item["activity_name"],
                "activity_name",
            )
            explanation = _require_text(
                item["explanation"],
                "explanation",
            )
        except (KeyError, TypeError) as exc:
            raise LLMServiceError(
                "LLM explanation detail is missing required fields."
            ) from exc

        if activity_name not in expected_names:
            raise LLMServiceError(
                f"LLM explanation invented an activity: {activity_name}"
            )
        if activity_name in details:
            raise LLMServiceError(
                f"LLM explanation duplicated an activity: {activity_name}"
            )
        details[activity_name] = explanation

    if set(details) != expected_names:
        raise LLMServiceError(
            "LLM explanation does not cover every recommendation."
        )

    return RecommendationExplanation(
        summary=summary,
        weather_context=weather_context,
        recommendation_details=details,
        fallback_note=fallback_note,
    )


def _require_text(
    value: Any,
    field_name: str,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise LLMServiceError(f"LLM field '{field_name}' must be text.")

    normalized = value.strip()
    if not normalized and not allow_empty:
        raise LLMServiceError(f"LLM field '{field_name}' cannot be empty.")
    return normalized
