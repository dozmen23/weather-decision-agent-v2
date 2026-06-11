"""End-to-end orchestration for agent, evaluation, and optional LLM output."""

from dataclasses import dataclass

from app.agent.decision_agent import AgentResult, DecisionAgent
from app.llm.client import StructuredLLMClient
from app.llm.explanation_service import (
    ExplanationService,
    RecommendationExplanation,
)
from app.llm.judge_service import LLMJudgeReport, LLMJudgeService
from app.models.user_preferences import UserPreferences
from evaluation.evaluator import (
    DeterministicEvaluator,
    EvaluationReport,
    EvaluationVerdict,
)


@dataclass(frozen=True)
class RecommendationWorkflowResult:
    """Complete output of the recommendation and evaluation workflow."""

    agent_result: AgentResult
    deterministic_evaluation: EvaluationReport
    explanation: RecommendationExplanation | None = None
    llm_judgment: LLMJudgeReport | None = None


class RecommendationService:
    """Run deterministic decision logic before optional LLM enrichment."""

    def __init__(
        self,
        agent: DecisionAgent | None = None,
        evaluator: DeterministicEvaluator | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.agent = agent or DecisionAgent()
        self.evaluator = evaluator or DeterministicEvaluator()
        self.explanation_service = (
            ExplanationService(llm_client) if llm_client is not None else None
        )
        self.judge_service = (
            LLMJudgeService(llm_client) if llm_client is not None else None
        )

    def recommend(
        self,
        city: str,
        preferences: UserPreferences,
        recommendation_limit: int = 3,
    ) -> RecommendationWorkflowResult:
        """Produce, verify, and optionally explain recommendations."""
        agent_result = self.agent.run(
            city,
            preferences,
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
            return RecommendationWorkflowResult(
                agent_result=agent_result,
                deterministic_evaluation=deterministic_report,
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

        return RecommendationWorkflowResult(
            agent_result=agent_result,
            deterministic_evaluation=deterministic_report,
            explanation=explanation,
            llm_judgment=llm_judgment,
        )
