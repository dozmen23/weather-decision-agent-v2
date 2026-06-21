"""Explainable scoring and ranking for eligible activities."""

from dataclasses import dataclass, field

from app.core.rules import evaluate_activity
from app.models.activity import Activity, CostLevel, WeatherSensitivity
from app.models.recommendation import RecommendationScoreBreakdown
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData, WeatherSeverity


@dataclass
class ScoreBreakdown:
    """Detailed scoring result for one activity candidate."""

    activity: Activity
    is_eligible: bool
    total_score: float
    score_breakdown: RecommendationScoreBreakdown = field(
        default_factory=RecommendationScoreBreakdown
    )
    weather_severity: WeatherSeverity | None = None
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
            score_breakdown=RecommendationScoreBreakdown(),
            weather_severity=weather.severity_level,
            warnings=rule_result.warnings,
            failed_rules=rule_result.failed_rules,
        )

    has_type_preference = bool(preferences.preferred_activity_type.strip())
    activity_type_score = (
        25.0
        if (
            not has_type_preference
            or activity.activity_type.casefold()
            == preferences.preferred_activity_type.casefold()
        )
        else 0.0
    )
    setting_score = 10.0 if activity.is_outdoor == preferences.prefers_outdoor else 0.0
    preference_match_score = activity_type_score + setting_score

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

    weather_safety_score = precipitation_score + wind_score
    practicality_score = _practicality_score(activity, weather, preferences)

    total_score = round(
        preference_match_score
        + temperature_score
        + weather_safety_score
        + practicality_score,
        2,
    )
    score_breakdown = RecommendationScoreBreakdown(
        weather_safety=round(weather_safety_score, 2),
        preference_match=round(preference_match_score, 2),
        comfort_match=round(temperature_score, 2),
        practicality=round(practicality_score, 2),
        total_score=total_score,
    )

    return ScoreBreakdown(
        activity=activity,
        is_eligible=True,
        total_score=total_score,
        score_breakdown=score_breakdown,
        weather_severity=weather.severity_level,
        activity_type_score=activity_type_score,
        setting_score=setting_score,
        temperature_score=temperature_score,
        precipitation_score=precipitation_score,
        wind_score=wind_score,
        explanations=_build_explanations(
            score_breakdown=score_breakdown,
            weather_severity=weather.severity_level,
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


def _practicality_score(
    activity: Activity,
    weather: WeatherData,
    preferences: UserPreferences,
) -> float:
    score = 15.0

    if activity.cost_level is CostLevel.MEDIUM:
        score -= 2.0
    elif activity.cost_level is CostLevel.HIGH:
        score -= 4.0

    if activity.requires_reservation:
        score -= 2.0

    if activity.duration_minutes > 180:
        score -= 2.0
    elif activity.duration_minutes < 20:
        score -= 1.0

    if not activity.is_outdoor:
        score -= preferences.indoor_feedback_penalty

    if activity.is_outdoor:
        if (
            weather.severity_level is WeatherSeverity.HIGH
            and activity.weather_sensitivity
            in {
                WeatherSensitivity.MODERATE,
                WeatherSensitivity.HIGH,
            }
        ):
            score -= 4.0
        elif (
            weather.severity_level is WeatherSeverity.MODERATE
            and activity.weather_sensitivity is WeatherSensitivity.HIGH
        ):
            score -= 2.0

    return round(max(0.0, score), 2)


def _build_explanations(
    score_breakdown: RecommendationScoreBreakdown,
    weather_severity: WeatherSeverity,
) -> list[str]:
    explanations = [
        f"Weather severity: {weather_severity.value}",
        f"Weather safety: {score_breakdown.weather_safety:.1f}/30",
        f"Preference match: {score_breakdown.preference_match:.1f}/35",
        f"Comfort match: {score_breakdown.comfort_match:.1f}/20",
        f"Practicality: {score_breakdown.practicality:.1f}/15",
        f"Total score: {score_breakdown.total_score:.1f}/100",
    ]
    return explanations
