"""Deterministic planner for the first autonomous decision loop."""

from dataclasses import dataclass, field
from enum import Enum

from app.core.scoring import ScoreBreakdown
from app.models.activity import Activity
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


class AgentAction(str, Enum):
    """Actions the planner can ask the decision agent to execute."""

    FETCH_WEATHER = "fetch_weather"
    LOAD_PREFERRED_CANDIDATES = "load_preferred_candidates"
    LOAD_BROADER_CANDIDATES = "load_broader_candidates"
    LOAD_SAFE_ALTERNATIVES = "load_safe_alternatives"
    SCORE_CANDIDATES = "score_candidates"
    FINALIZE = "finalize"
    STOP_NO_RESULT = "stop_no_result"


class SearchStrategy(str, Enum):
    """Candidate search strategy currently represented in agent state."""

    NOT_STARTED = "not_started"
    PREFERRED = "preferred"
    BROADER = "broader"
    SAFE_ALTERNATIVES = "safe_alternatives"


@dataclass
class AgentState:
    """Mutable information observed and produced during one agent run."""

    city: str
    preferences: UserPreferences
    weather: WeatherData | None = None
    candidates: list[Activity] = field(default_factory=list)
    ranked_candidates: list[ScoreBreakdown] = field(default_factory=list)
    search_strategy: SearchStrategy = SearchStrategy.NOT_STARTED
    scoring_completed: bool = False


class DecisionPlanner:
    """Choose the next action from the current state of the run."""

    def choose_next_action(self, state: AgentState) -> AgentAction:
        """Return the next tool call or terminal action."""
        if state.weather is None:
            return AgentAction.FETCH_WEATHER

        if state.search_strategy is SearchStrategy.NOT_STARTED:
            return AgentAction.LOAD_PREFERRED_CANDIDATES

        if not state.scoring_completed:
            return AgentAction.SCORE_CANDIDATES

        if state.ranked_candidates:
            return AgentAction.FINALIZE

        if state.search_strategy is SearchStrategy.PREFERRED:
            return AgentAction.LOAD_BROADER_CANDIDATES

        if (
            state.search_strategy is SearchStrategy.BROADER
            and state.preferences.prefers_outdoor
        ):
            return AgentAction.LOAD_SAFE_ALTERNATIVES

        return AgentAction.STOP_NO_RESULT
