"""Autonomous tool-using decision loop for weather recommendations."""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.agent.planner import (
    AgentAction,
    AgentState,
    DecisionPlanner,
    SearchStrategy,
)
from app.core.scoring import rank_activities
from app.models.activity import Activity
from app.models.recommendation import Recommendation
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from app.services.activity_service import ActivityService
from app.services.weather_service import WeatherService


class WeatherTool(Protocol):
    """Tool contract used by the agent to retrieve weather."""

    def get_current_weather(self, city: str) -> WeatherData:
        """Return normalized current weather for a city."""

    def get_weather_for_date(
        self,
        city: str,
        target_date: date,
    ) -> WeatherData:
        """Return normalized forecast weather for a city and date."""


class ActivityCatalogTool(Protocol):
    """Tool contract used by the agent to retrieve activity candidates."""

    def find_candidates(
        self,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> list[Activity]:
        """Return activities matching optional filters."""


@dataclass(frozen=True)
class AgentTraceStep:
    """One observable decision or tool call made by the agent."""

    action: AgentAction
    detail: str


@dataclass
class AgentResult:
    """Terminal output of one autonomous decision run."""

    status: str
    weather: WeatherData
    recommendations: list[Recommendation] = field(default_factory=list)
    trace: list[AgentTraceStep] = field(default_factory=list)
    used_safe_fallback: bool = False
    message: str = ""


class AgentExecutionError(RuntimeError):
    """Raised when the decision loop cannot reach a terminal state safely."""


class DecisionAgent:
    """Coordinate planning, tool use, scoring, and fallback decisions."""

    def __init__(
        self,
        weather_tool: WeatherTool | None = None,
        activity_tool: ActivityCatalogTool | None = None,
        planner: DecisionPlanner | None = None,
        max_steps: int = 12,
    ) -> None:
        self.weather_tool = weather_tool or WeatherService()
        self.activity_tool = activity_tool or ActivityService()
        self.planner = planner or DecisionPlanner()
        self.max_steps = max_steps

    def run(
        self,
        city: str,
        preferences: UserPreferences,
        recommendation_limit: int = 3,
        target_date: date | None = None,
    ) -> AgentResult:
        """Run the autonomous loop until recommendations or a safe stop."""
        state = AgentState(
            city=city,
            preferences=preferences,
            target_date=target_date,
        )
        trace: list[AgentTraceStep] = []

        for _ in range(self.max_steps):
            action = self.planner.choose_next_action(state)

            if action is AgentAction.FETCH_WEATHER:
                if state.target_date is None:
                    state.weather = self.weather_tool.get_current_weather(
                        state.city
                    )
                    weather_detail = (
                        f"Retrieved current weather for {state.weather.city}."
                    )
                else:
                    state.weather = self.weather_tool.get_weather_for_date(
                        state.city,
                        state.target_date,
                    )
                    weather_detail = (
                        f"Retrieved forecast for {state.weather.city} on "
                        f"{state.target_date.isoformat()}."
                    )
                trace.append(
                    AgentTraceStep(
                        action,
                        weather_detail,
                    )
                )
                continue

            if action is AgentAction.LOAD_PREFERRED_CANDIDATES:
                self._load_candidates(
                    state,
                    activity_type=preferences.preferred_activity_type,
                    is_outdoor=preferences.prefers_outdoor,
                    strategy=SearchStrategy.PREFERRED,
                )
                trace.append(
                    AgentTraceStep(
                        action,
                        f"Loaded {len(state.candidates)} exact preference candidates.",
                    )
                )
                continue

            if action is AgentAction.LOAD_BROADER_CANDIDATES:
                self._load_candidates(
                    state,
                    is_outdoor=preferences.prefers_outdoor,
                    strategy=SearchStrategy.BROADER,
                )
                trace.append(
                    AgentTraceStep(
                        action,
                        f"Broadened search to {len(state.candidates)} candidates "
                        "with the preferred setting.",
                    )
                )
                continue

            if action is AgentAction.LOAD_SAFE_ALTERNATIVES:
                self._load_candidates(
                    state,
                    is_outdoor=False,
                    strategy=SearchStrategy.SAFE_ALTERNATIVES,
                )
                trace.append(
                    AgentTraceStep(
                        action,
                        f"Weather-compatible search loaded "
                        f"{len(state.candidates)} indoor alternatives.",
                    )
                )
                continue

            if action is AgentAction.SCORE_CANDIDATES:
                if state.weather is None:
                    raise AgentExecutionError(
                        "Planner requested scoring before weather was available."
                    )
                state.ranked_candidates = rank_activities(
                    state.weather,
                    state.preferences,
                    state.candidates,
                )
                state.scoring_completed = True
                trace.append(
                    AgentTraceStep(
                        action,
                        f"{len(state.ranked_candidates)} candidates passed rules "
                        "and were ranked.",
                    )
                )
                continue

            if action is AgentAction.FINALIZE:
                return self._build_success_result(
                    state,
                    trace,
                    recommendation_limit,
                )

            if action is AgentAction.STOP_NO_RESULT:
                if state.weather is None:
                    raise AgentExecutionError(
                        "Planner stopped before weather was available."
                    )
                trace.append(
                    AgentTraceStep(
                        action,
                        "Stopped after all planned search strategies produced "
                        "no eligible activity.",
                    )
                )
                return AgentResult(
                    status="no_recommendation",
                    weather=state.weather,
                    trace=trace,
                    used_safe_fallback=(
                        state.search_strategy is SearchStrategy.SAFE_ALTERNATIVES
                    ),
                    message=(
                        "No activity satisfied the current weather and preference "
                        "constraints."
                    ),
                )

        raise AgentExecutionError(
            f"Decision loop exceeded the maximum of {self.max_steps} steps."
        )

    def _load_candidates(
        self,
        state: AgentState,
        strategy: SearchStrategy,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> None:
        state.candidates = self.activity_tool.find_candidates(
            activity_type=activity_type,
            is_outdoor=is_outdoor,
        )
        state.ranked_candidates = []
        state.search_strategy = strategy
        state.scoring_completed = False

    @staticmethod
    def _build_success_result(
        state: AgentState,
        trace: list[AgentTraceStep],
        recommendation_limit: int,
    ) -> AgentResult:
        if state.weather is None:
            raise AgentExecutionError(
                "Planner finalized before weather was available."
            )

        selected_candidates = state.ranked_candidates[: max(1, recommendation_limit)]
        recommendations = [
            Recommendation(
                activity=result.activity,
                score=result.total_score,
                reasoning="; ".join(result.explanations),
                warnings=result.warnings,
            )
            for result in selected_candidates
        ]
        trace.append(
            AgentTraceStep(
                AgentAction.FINALIZE,
                f"Selected {len(recommendations)} final recommendations.",
            )
        )

        return AgentResult(
            status="completed",
            weather=state.weather,
            recommendations=recommendations,
            trace=trace,
            used_safe_fallback=(
                state.search_strategy is SearchStrategy.SAFE_ALTERNATIVES
            ),
            message="Recommendations were produced successfully.",
        )
