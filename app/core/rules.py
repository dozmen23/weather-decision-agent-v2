"""Deterministic eligibility rules for candidate activities."""

from dataclasses import dataclass, field

from app.models.activity import Activity
from app.models.activity import ActivityIntensity, CostLevel, TransportEase
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData, WeatherSeverity


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

    if (
        preferences.preferred_activity_type.strip()
        and activity.activity_type.casefold()
        != preferences.preferred_activity_type.casefold()
    ):
        warnings.append("Activity type does not match the user's first preference.")

    if activity.is_outdoor != preferences.prefers_outdoor:
        warnings.append("Indoor/outdoor setting does not match the user's preference.")

    _check_practical_preferences(preferences, activity, failed_rules)

    if activity.is_outdoor:
        _check_weather_severity(weather, failed_rules, warnings)
        _check_temperature(weather, preferences, activity, failed_rules)
        _check_precipitation(weather, preferences, activity, failed_rules)
        _check_wind(weather, preferences, activity, failed_rules)

    return RuleEvaluation(
        is_eligible=not failed_rules,
        failed_rules=failed_rules,
        warnings=warnings,
    )


def _check_weather_severity(
    weather: WeatherData,
    failed_rules: list[str],
    warnings: list[str],
) -> None:
    if weather.severity_level is WeatherSeverity.SEVERE:
        failed_rules.append(
            "Weather severity is too high for outdoor activities."
        )
        return

    if weather.severity_level is WeatherSeverity.HIGH:
        warnings.append(
            "Weather risk is high; a safer indoor alternative may be better."
        )
    elif weather.severity_level is WeatherSeverity.MODERATE:
        warnings.append(
            "Weather risk is moderate; check conditions before going outside."
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


def _check_practical_preferences(
    preferences: UserPreferences,
    activity: Activity,
    failed_rules: list[str],
) -> None:
    if _cost_rank(activity.cost_level) > _cost_rank(preferences.max_cost_level):
        failed_rules.append("Activity cost exceeds the user's budget preference.")

    if activity.duration_minutes > preferences.max_duration_minutes:
        failed_rules.append("Activity duration exceeds the user's time preference.")

    if preferences.avoid_reservations and activity.requires_reservation:
        failed_rules.append("Activity requires a reservation.")

    if not _is_suitable_for_preference(activity, preferences.suitable_for):
        failed_rules.append("Activity is not suitable for the selected company.")

    if _transport_rank(activity.transport_ease) > _transport_rank(
        preferences.max_transport_ease
    ):
        failed_rules.append("Activity is harder to access than the user's preference.")

    if preferences.preferred_intensity is None:
        return

    if _intensity_rank(activity.intensity) > _intensity_rank(
        preferences.preferred_intensity
    ):
        failed_rules.append("Activity intensity exceeds the user's preference.")


def _cost_rank(cost_level: CostLevel) -> int:
    return {
        CostLevel.FREE: 0,
        CostLevel.LOW: 1,
        CostLevel.MEDIUM: 2,
        CostLevel.HIGH: 3,
    }[cost_level]


def _intensity_rank(intensity: ActivityIntensity) -> int:
    return {
        ActivityIntensity.LOW: 0,
        ActivityIntensity.MODERATE: 1,
        ActivityIntensity.HIGH: 2,
    }[intensity]


def _transport_rank(transport_ease: TransportEase) -> int:
    return {
        TransportEase.EASY: 0,
        TransportEase.MODERATE: 1,
        TransportEase.HARD: 2,
    }[transport_ease]


def _is_suitable_for_preference(
    activity: Activity,
    suitable_for: str | None,
) -> bool:
    if suitable_for is None:
        return True

    labels = set(activity.suitable_for)
    accepted_labels = {
        "solo": {"solo", "beginners", "students", "remote workers"},
        "friends": {
            "friends",
            "groups",
            "teams",
            "couples",
            "athletes",
            "fitness enthusiasts",
            "photographers",
        },
        "families": {"families", "seniors"},
    }.get(suitable_for, {suitable_for})

    return bool(labels & accepted_labels)
