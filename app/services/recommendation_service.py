"""End-to-end orchestration for agent, evaluation, and optional LLM output."""

from dataclasses import dataclass, replace
from datetime import date

from app.agent.decision_agent import (
    AgentResult,
    AgentTraceStep,
    DecisionAgent,
)
from app.agent.planner import AgentAction
from app.core.scoring import rank_activities
from app.llm.activity_generation_service import ActivityGenerationService
from app.llm.client import LLMServiceError, StructuredLLMClient
from app.llm.explanation_service import (
    ExplanationService,
    RecommendationExplanation,
)
from app.llm.judge_service import LLMJudgeReport, LLMJudgeService
from app.models.activity import Activity
from app.models.recommendation import Recommendation
from app.models.recommendation_history import (
    FeedbackValue,
    RecommendationHistoryItem,
    RecommendationHistoryRecord,
    new_history_record_id,
    utc_timestamp,
)
from app.models.user_preferences import UserPreferences
from app.services.history_service import (
    RecommendationHistoryError,
    RecommendationHistoryRepository,
)
from evaluation.evaluator import (
    DeterministicEvaluator,
    EvaluationReport,
    EvaluationVerdict,
)


INDOOR_FEEDBACK_PENALTY = 2.0
PERSONALIZATION_HISTORY_LIMIT = 20
PERSONALIZATION_NEGATIVE_THRESHOLD = 2


@dataclass(frozen=True)
class RecommendationWorkflowResult:
    """Complete output of the recommendation and evaluation workflow."""

    agent_result: AgentResult
    deterministic_evaluation: EvaluationReport
    preferences: UserPreferences | None = None
    explanation: RecommendationExplanation | None = None
    llm_judgment: LLMJudgeReport | None = None
    history_record: RecommendationHistoryRecord | None = None


class RecommendationService:
    """Run deterministic decision logic before optional LLM enrichment."""

    def __init__(
        self,
        agent: DecisionAgent | None = None,
        evaluator: DeterministicEvaluator | None = None,
        llm_client: StructuredLLMClient | None = None,
        history_repository: RecommendationHistoryRepository | None = None,
    ) -> None:
        self.agent = agent or DecisionAgent()
        self.evaluator = evaluator or DeterministicEvaluator()
        self.history_repository = history_repository
        self.explanation_service = (
            ExplanationService(llm_client) if llm_client is not None else None
        )
        self.judge_service = (
            LLMJudgeService(llm_client) if llm_client is not None else None
        )
        self.activity_generation_service = (
            ActivityGenerationService(llm_client)
            if llm_client is not None
            else None
        )

    def recommend(
        self,
        city: str,
        preferences: UserPreferences,
        recommendation_limit: int = 3,
        target_date: date | None = None,
    ) -> RecommendationWorkflowResult:
        """Produce, verify, and optionally explain recommendations."""
        preferences = self._personalize_preferences(preferences)

        if target_date is None:
            agent_result = self.agent.run(
                city,
                preferences,
                recommendation_limit=recommendation_limit,
            )
        else:
            agent_result = self.agent.run(
                city,
                preferences,
                recommendation_limit=recommendation_limit,
                target_date=target_date,
            )
        deterministic_report = self.evaluator.evaluate(
            agent_result,
            preferences,
        )

        if (
            deterministic_report.verdict is EvaluationVerdict.NO_RECOMMENDATION
            and self.activity_generation_service is not None
        ):
            try:
                generated_activities = self.activity_generation_service.generate(
                    agent_result.weather,
                    preferences,
                    limit=max(3, recommendation_limit),
                )
            except LLMServiceError:
                workflow_result = RecommendationWorkflowResult(
                    agent_result=agent_result,
                    deterministic_evaluation=deterministic_report,
                    preferences=preferences,
                )
                return self._store_history(
                    workflow_result,
                    city,
                    preferences,
                    target_date,
                )
            agent_result = _build_generated_candidate_result(
                original_result=agent_result,
                generated_activities=generated_activities,
                preferences=preferences,
                recommendation_limit=recommendation_limit,
            )
            deterministic_report = self.evaluator.evaluate(
                agent_result,
                preferences,
            )

        if (
            self.explanation_service is None
            or self.judge_service is None
            or deterministic_report.verdict is EvaluationVerdict.REJECTED
        ):
            workflow_result = RecommendationWorkflowResult(
                agent_result=agent_result,
                deterministic_evaluation=deterministic_report,
                preferences=preferences,
            )
            return self._store_history(
                workflow_result,
                city,
                preferences,
                target_date,
            )

        explanation = self.explanation_service.generate(
            agent_result,
            preferences,
            deterministic_report,
        )
        llm_judgment = self.judge_service.evaluate(
            agent_result,
            preferences,
            deterministic_report,
        )

        workflow_result = RecommendationWorkflowResult(
            agent_result=agent_result,
            deterministic_evaluation=deterministic_report,
            preferences=preferences,
            explanation=explanation,
            llm_judgment=llm_judgment,
        )
        return self._store_history(
            workflow_result,
            city,
            preferences,
            target_date,
        )

    def _store_history(
        self,
        workflow_result: RecommendationWorkflowResult,
        city: str,
        preferences: UserPreferences,
        target_date: date | None,
    ) -> RecommendationWorkflowResult:
        if self.history_repository is None:
            return workflow_result

        history_record = self.history_repository.append(
            _build_history_record(
                workflow_result=workflow_result,
                city=city,
                preferences=preferences,
                target_date=target_date,
            )
        )
        return RecommendationWorkflowResult(
            agent_result=workflow_result.agent_result,
            deterministic_evaluation=workflow_result.deterministic_evaluation,
            preferences=workflow_result.preferences,
            explanation=workflow_result.explanation,
            llm_judgment=workflow_result.llm_judgment,
            history_record=history_record,
        )

    def _personalize_preferences(
        self,
        preferences: UserPreferences,
    ) -> UserPreferences:
        if self.history_repository is None:
            return preferences

        try:
            recent_records = self.history_repository.list_recent(
                limit=PERSONALIZATION_HISTORY_LIMIT
            )
        except RecommendationHistoryError:
            return preferences

        negative_indoor = 0
        positive_indoor = 0
        for record in recent_records:
            if record.feedback is None:
                continue
            has_indoor_recommendation = any(
                not item.is_outdoor for item in record.recommendations
            )
            if not has_indoor_recommendation:
                continue

            if record.feedback is FeedbackValue.NEGATIVE:
                negative_indoor += 1
            elif record.feedback is FeedbackValue.POSITIVE:
                positive_indoor += 1

        if negative_indoor - positive_indoor < PERSONALIZATION_NEGATIVE_THRESHOLD:
            return preferences

        return replace(
            preferences,
            indoor_feedback_penalty=INDOOR_FEEDBACK_PENALTY,
        )


def _build_generated_candidate_result(
    *,
    original_result: AgentResult,
    generated_activities: list[Activity],
    preferences: UserPreferences,
    recommendation_limit: int,
) -> AgentResult:
    trace = _trace_before_terminal_stop(original_result.trace)
    trace.append(
        AgentTraceStep(
            AgentAction.LOAD_GENERATED_CANDIDATES,
            f"Loaded {len(generated_activities)} LLM-generated candidates.",
        )
    )
    ranked_candidates = rank_activities(
        original_result.weather,
        preferences,
        generated_activities,
    )
    trace.append(
        AgentTraceStep(
            AgentAction.SCORE_CANDIDATES,
            f"{len(ranked_candidates)} generated candidates passed rules "
            "and were ranked.",
        )
    )

    if not ranked_candidates:
        trace.append(
            AgentTraceStep(
                AgentAction.STOP_NO_RESULT,
                "Stopped after generated candidates produced no eligible activity.",
            )
        )
        return AgentResult(
            status="no_recommendation",
            weather=original_result.weather,
            trace=trace,
            used_safe_fallback=True,
            message=(
                "No catalog or generated activity satisfied the current weather "
                "and preference constraints."
            ),
        )

    selected_candidates = ranked_candidates[: max(1, recommendation_limit)]
    recommendations = [
        Recommendation(
            activity=result.activity,
            score=result.total_score,
            reasoning="; ".join(result.explanations),
            score_breakdown=result.score_breakdown,
            warnings=result.warnings,
        )
        for result in selected_candidates
    ]
    trace.append(
        AgentTraceStep(
            AgentAction.FINALIZE,
            f"Selected {len(recommendations)} generated recommendations.",
        )
    )

    return AgentResult(
        status="completed",
        weather=original_result.weather,
        recommendations=recommendations,
        trace=trace,
        used_safe_fallback=True,
        message=(
            "Recommendations were produced from generated candidates after "
            "deterministic safety validation."
        ),
    )


def _trace_before_terminal_stop(
    trace: list[AgentTraceStep],
) -> list[AgentTraceStep]:
    if trace and trace[-1].action is AgentAction.STOP_NO_RESULT:
        return list(trace[:-1])
    return list(trace)


def _build_history_record(
    *,
    workflow_result: RecommendationWorkflowResult,
    city: str,
    preferences: UserPreferences,
    target_date: date | None,
) -> RecommendationHistoryRecord:
    agent_result = workflow_result.agent_result
    weather = agent_result.weather

    return RecommendationHistoryRecord(
        record_id=new_history_record_id(),
        created_at=utc_timestamp(),
        city=city,
        target_date=target_date.isoformat() if target_date else None,
        status=agent_result.status,
        used_safe_fallback=agent_result.used_safe_fallback,
        used_generated_candidates=any(
            step.action is AgentAction.LOAD_GENERATED_CANDIDATES
            for step in agent_result.trace
        ),
        weather={
            "city": weather.city,
            "forecast_date": (
                weather.forecast_date.isoformat()
                if weather.forecast_date
                else None
            ),
            "temperature_celsius": weather.temperature_celsius,
            "minimum_temperature_celsius": weather.minimum_temperature_celsius,
            "maximum_temperature_celsius": weather.maximum_temperature_celsius,
            "precipitation_probability_percent": (
                weather.precipitation_probability_percent
            ),
            "wind_speed_kmh": weather.wind_speed_kmh,
            "condition": weather.condition,
            "severity_level": weather.severity_level.value,
        },
        preferences={
            "preferred_activity_type": preferences.preferred_activity_type,
            "prefers_outdoor": preferences.prefers_outdoor,
            "min_temperature_celsius": preferences.min_temperature_celsius,
            "max_temperature_celsius": preferences.max_temperature_celsius,
            "max_precipitation_probability_percent": (
                preferences.max_precipitation_probability_percent
            ),
            "max_wind_speed_kmh": preferences.max_wind_speed_kmh,
            "max_cost_level": preferences.max_cost_level.value,
            "max_duration_minutes": preferences.max_duration_minutes,
            "preferred_intensity": (
                preferences.preferred_intensity.value
                if preferences.preferred_intensity
                else None
            ),
            "avoid_reservations": preferences.avoid_reservations,
            "suitable_for": preferences.suitable_for,
            "indoor_feedback_penalty": preferences.indoor_feedback_penalty,
        },
        recommendations=[
            RecommendationHistoryItem(
                activity_name=recommendation.activity.name,
                activity_type=recommendation.activity.activity_type,
                is_outdoor=recommendation.activity.is_outdoor,
                score=recommendation.score,
            )
            for recommendation in agent_result.recommendations
        ],
    )
