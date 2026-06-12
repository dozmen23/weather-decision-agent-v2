"""Tests for the autonomous decision loop."""

import unittest
from datetime import date

from app.agent.decision_agent import DecisionAgent
from app.agent.planner import AgentAction
from app.models.activity import Activity
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


class StubWeatherTool:
    def __init__(self, weather: WeatherData) -> None:
        self.weather = weather
        self.requested_cities: list[str] = []
        self.requested_dates: list[date] = []

    def get_current_weather(self, city: str) -> WeatherData:
        self.requested_cities.append(city)
        return self.weather

    def get_weather_for_date(
        self,
        city: str,
        target_date: date,
    ) -> WeatherData:
        self.requested_cities.append(city)
        self.requested_dates.append(target_date)
        return self.weather


class StubActivityTool:
    def __init__(self, activities: list[Activity]) -> None:
        self.activities = activities
        self.calls: list[tuple[str | None, bool | None]] = []

    def find_candidates(
        self,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> list[Activity]:
        self.calls.append((activity_type, is_outdoor))
        candidates = self.activities

        if activity_type is not None:
            candidates = [
                activity
                for activity in candidates
                if activity.activity_type.casefold() == activity_type.casefold()
            ]

        if is_outdoor is not None:
            candidates = [
                activity
                for activity in candidates
                if activity.is_outdoor is is_outdoor
            ]

        return candidates


class DecisionAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preferences = UserPreferences(
            preferred_activity_type="Walking",
            prefers_outdoor=True,
            min_temperature_celsius=15,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        self.park_walk = Activity(
            "Park Walk",
            "walking",
            True,
            8,
            32,
            45,
            30,
        )
        self.cycling = Activity(
            "Coastal Cycling",
            "cycling",
            True,
            12,
            30,
            25,
            22,
        )
        self.museum = Activity(
            "Museum Visit",
            "culture",
            False,
            -20,
            50,
            100,
            100,
        )

    def test_agent_finishes_when_preferred_candidate_is_eligible(self) -> None:
        weather_tool = StubWeatherTool(
            WeatherData("Istanbul", 22.5, 5, 5, "Clear sky")
        )
        activity_tool = StubActivityTool(
            [self.park_walk, self.cycling, self.museum]
        )

        result = DecisionAgent(weather_tool, activity_tool).run(
            "Istanbul",
            self.preferences,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.recommendations[0].activity.name, "Park Walk")
        self.assertFalse(result.used_safe_fallback)
        self.assertEqual(
            [step.action for step in result.trace],
            [
                AgentAction.FETCH_WEATHER,
                AgentAction.LOAD_PREFERRED_CANDIDATES,
                AgentAction.SCORE_CANDIDATES,
                AgentAction.FINALIZE,
            ],
        )

    def test_agent_replans_to_indoor_options_after_bad_weather(self) -> None:
        weather_tool = StubWeatherTool(
            WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")
        )
        activity_tool = StubActivityTool(
            [self.park_walk, self.cycling, self.museum]
        )

        result = DecisionAgent(weather_tool, activity_tool).run(
            "Istanbul",
            self.preferences,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.recommendations[0].activity.name, "Museum Visit")
        self.assertTrue(result.used_safe_fallback)
        self.assertIn(
            AgentAction.LOAD_BROADER_CANDIDATES,
            [step.action for step in result.trace],
        )
        self.assertIn(
            AgentAction.LOAD_SAFE_ALTERNATIVES,
            [step.action for step in result.trace],
        )

    def test_agent_stops_safely_when_no_strategy_finds_candidates(self) -> None:
        weather_tool = StubWeatherTool(
            WeatherData("Istanbul", 18, 90, 45, "Thunderstorm")
        )
        activity_tool = StubActivityTool([self.park_walk])

        result = DecisionAgent(weather_tool, activity_tool).run(
            "Istanbul",
            self.preferences,
        )

        self.assertEqual(result.status, "no_recommendation")
        self.assertEqual(result.recommendations, [])
        self.assertTrue(result.used_safe_fallback)
        self.assertEqual(result.trace[-1].action, AgentAction.STOP_NO_RESULT)

    def test_agent_uses_selected_forecast_date(self) -> None:
        selected_date = date(2026, 6, 15)
        weather_tool = StubWeatherTool(
            WeatherData(
                "Istanbul",
                22.5,
                5,
                5,
                "Clear sky",
                forecast_date=selected_date,
            )
        )

        result = DecisionAgent(
            weather_tool,
            StubActivityTool([self.park_walk]),
        ).run(
            "Istanbul",
            self.preferences,
            target_date=selected_date,
        )

        self.assertEqual(weather_tool.requested_dates, [selected_date])
        self.assertEqual(result.weather.forecast_date, selected_date)
        self.assertIn(selected_date.isoformat(), result.trace[0].detail)


if __name__ == "__main__":
    unittest.main()
