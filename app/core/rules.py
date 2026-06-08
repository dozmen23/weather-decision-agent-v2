"""Deterministic eligibility rules for candidate activities."""

from dataclasses import dataclass, field

from app.models.activity import Activity
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


@dataclass
class RuleEvaluation:
    """Result of applying hard constraints and preference checks."""

    is_eligible: bool
    failed_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def evaluate_activity(
    weather: WeatherData,
    preferences: UserPreferences,
    activity: Activity,
) -> RuleEvaluation:
    """Evaluate whether an activity can remain a recommendation candidate."""
    failed_rules: list[str] = []
    warnings: list[str] = []

    if activity.activity_type != preferences.preferred_activity_type:
        warnings.append("Activity type does not match the user's first preference.")

    if activity.is_outdoor != preferences.prefers_outdoor:
        warnings.append("Indoor/outdoor setting does not match the user's preference.")

    if activity.is_outdoor:
        _check_temperature(weather, preferences, activity, failed_rules)
        _check_precipitation(weather, preferences, activity, failed_rules)
        _check_wind(weather, preferences, activity, failed_rules)

    return RuleEvaluation(
        is_eligible=not failed_rules,
        failed_rules=failed_rules,
        warnings=warnings,
    )


def _check_temperature(
    weather: WeatherData,
    preferences: UserPreferences,
    activity: Activity,
    failed_rules: list[str],
) -> None:
    temperature = weather.temperature_celsius

    if not (
        activity.min_temperature_celsius
        <= temperature
        <= activity.max_temperature_celsius
    ):
        failed_rules.append("Temperature is outside the activity's safe range.")

    if not (
        preferences.min_temperature_celsius
        <= temperature
        <= preferences.max_temperature_celsius
    ):
        failed_rules.append("Temperature is outside the user's comfort range.")


def _check_precipitation(
    weather: WeatherData,
    preferences: UserPreferences,
    activity: Activity,
    failed_rules: list[str],
) -> None:
    precipitation = weather.precipitation_probability_percent

    if precipitation > activity.max_precipitation_probability_percent:
        failed_rules.append("Precipitation risk is too high for the activity.")

    if precipitation > preferences.max_precipitation_probability_percent:
        failed_rules.append("Precipitation risk exceeds the user's limit.")


def _check_wind(
    weather: WeatherData,
    preferences: UserPreferences,
    activity: Activity,
    failed_rules: list[str],
) -> None:
    wind_speed = weather.wind_speed_kmh

    if wind_speed > activity.max_wind_speed_kmh:
        failed_rules.append("Wind speed is too high for the activity.")

    if wind_speed > preferences.max_wind_speed_kmh:
        failed_rules.append("Wind speed exceeds the user's limit.")
