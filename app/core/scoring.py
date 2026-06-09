"""Explainable scoring and ranking for eligible activities."""

from dataclasses import dataclass, field

from app.core.rules import evaluate_activity
from app.models.activity import Activity
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


@dataclass
class ScoreBreakdown:
    """Detailed scoring result for one activity candidate."""

    activity: Activity
    is_eligible: bool
    total_score: float
    activity_type_score: float = 0.0
    setting_score: float = 0.0
    temperature_score: float = 0.0
    precipitation_score: float = 0.0
    wind_score: float = 0.0
    explanations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failed_rules: list[str] = field(default_factory=list)


def score_activity(
    weather: WeatherData,
    preferences: UserPreferences,
    activity: Activity,
) -> ScoreBreakdown:
    """Score one candidate after applying deterministic eligibility rules."""
    rule_result = evaluate_activity(weather, preferences, activity)

    if not rule_result.is_eligible:
        return ScoreBreakdown(
            activity=activity,
            is_eligible=False,
            total_score=0.0,
            warnings=rule_result.warnings,
            failed_rules=rule_result.failed_rules,
        )

    activity_type_score = (
        30.0
        if (
            activity.activity_type.casefold()
            == preferences.preferred_activity_type.casefold()
        )
        else 0.0
    )
    setting_score = 20.0 if activity.is_outdoor == preferences.prefers_outdoor else 0.0

    if activity.is_outdoor:
        temperature_score = _temperature_score(weather, preferences)
        precipitation_score = _remaining_margin_score(
            value=weather.precipitation_probability_percent,
            limit=min(
                activity.max_precipitation_probability_percent,
                preferences.max_precipitation_probability_percent,
            ),
            maximum_score=15.0,
        )
        wind_score = _remaining_margin_score(
            value=weather.wind_speed_kmh,
            limit=min(
                activity.max_wind_speed_kmh,
                preferences.max_wind_speed_kmh,
            ),
            maximum_score=15.0,
        )
    else:
        temperature_score = 20.0
        precipitation_score = 15.0
        wind_score = 15.0

    total_score = round(
        activity_type_score
        + setting_score
        + temperature_score
        + precipitation_score
        + wind_score,
        2,
    )

    return ScoreBreakdown(
        activity=activity,
        is_eligible=True,
        total_score=total_score,
        activity_type_score=activity_type_score,
        setting_score=setting_score,
        temperature_score=temperature_score,
        precipitation_score=precipitation_score,
        wind_score=wind_score,
        explanations=_build_explanations(
            activity_type_score=activity_type_score,
            setting_score=setting_score,
            temperature_score=temperature_score,
            precipitation_score=precipitation_score,
            wind_score=wind_score,
        ),
        warnings=rule_result.warnings,
    )


def rank_activities(
    weather: WeatherData,
    preferences: UserPreferences,
    activities: list[Activity],
) -> list[ScoreBreakdown]:
    """Return eligible activity candidates ordered from best to worst."""
    scored_activities = [
        score_activity(weather, preferences, activity) for activity in activities
    ]
    eligible_activities = [
        result for result in scored_activities if result.is_eligible
    ]

    return sorted(
        eligible_activities,
        key=lambda result: (-result.total_score, result.activity.name),
    )


def _temperature_score(
    weather: WeatherData,
    preferences: UserPreferences,
) -> float:
    comfort_minimum = preferences.min_temperature_celsius
    comfort_maximum = preferences.max_temperature_celsius
    comfort_midpoint = (comfort_minimum + comfort_maximum) / 2
    half_range = (comfort_maximum - comfort_minimum) / 2

    if half_range <= 0:
        return 20.0

    distance_from_midpoint = abs(
        weather.temperature_celsius - comfort_midpoint
    )
    ratio = max(0.0, 1 - (distance_from_midpoint / half_range))
    return round(20.0 * ratio, 2)


def _remaining_margin_score(
    value: float,
    limit: float,
    maximum_score: float,
) -> float:
    if limit <= 0:
        return maximum_score if value <= 0 else 0.0

    ratio = max(0.0, 1 - (value / limit))
    return round(maximum_score * ratio, 2)


def _build_explanations(
    activity_type_score: float,
    setting_score: float,
    temperature_score: float,
    precipitation_score: float,
    wind_score: float,
) -> list[str]:
    explanations = [
        f"Activity type match: {activity_type_score:.1f}/30",
        f"Indoor/outdoor preference match: {setting_score:.1f}/20",
        f"Temperature comfort: {temperature_score:.1f}/20",
        f"Precipitation margin: {precipitation_score:.1f}/15",
        f"Wind margin: {wind_score:.1f}/15",
    ]
    return explanations
