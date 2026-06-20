"""Generate controlled activity candidates without bypassing safety rules."""

import json
from typing import Any

from app.llm.client import LLMServiceError, StructuredLLMClient
from app.models.activity import (
    Activity,
    ActivityIntensity,
    CostLevel,
    TransportEase,
    WeatherSensitivity,
)
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData


ACTIVITY_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "activities": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "activity_type": {"type": "string"},
                    "is_outdoor": {"type": "boolean"},
                    "min_temperature_celsius": {"type": "number"},
                    "max_temperature_celsius": {"type": "number"},
                    "max_precipitation_probability_percent": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "max_wind_speed_kmh": {
                        "type": "number",
                        "minimum": 0,
                    },
                    "purpose": {"type": "string"},
                    "intensity": {
                        "type": "string",
                        "enum": ["low", "moderate", "high"],
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "minimum": 10,
                        "maximum": 240,
                    },
                    "cost_level": {
                        "type": "string",
                        "enum": ["free", "low", "medium", "high"],
                    },
                    "weather_sensitivity": {
                        "type": "string",
                        "enum": ["none", "low", "moderate", "high"],
                    },
                    "requires_reservation": {"type": "boolean"},
                    "transport_ease": {
                        "type": "string",
                        "enum": ["easy", "moderate", "hard"],
                    },
                    "suitable_for": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 6,
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 8,
                    },
                },
                "required": [
                    "name",
                    "activity_type",
                    "is_outdoor",
                    "min_temperature_celsius",
                    "max_temperature_celsius",
                    "max_precipitation_probability_percent",
                    "max_wind_speed_kmh",
                    "purpose",
                    "intensity",
                    "duration_minutes",
                    "cost_level",
                    "weather_sensitivity",
                    "requires_reservation",
                    "suitable_for",
                    "tags",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["activities"],
    "additionalProperties": False,
}

ALLOWED_ACTIVITY_FIELDS = {
    "name",
    "activity_type",
    "is_outdoor",
    "min_temperature_celsius",
    "max_temperature_celsius",
    "max_precipitation_probability_percent",
    "max_wind_speed_kmh",
    "purpose",
    "intensity",
    "duration_minutes",
    "cost_level",
    "weather_sensitivity",
    "requires_reservation",
    "transport_ease",
    "suitable_for",
    "tags",
}


class ActivityGenerationService:
    """Ask an LLM for candidates that the deterministic system will verify."""

    def __init__(self, client: StructuredLLMClient) -> None:
        self.client = client

    def generate(
        self,
        weather: WeatherData,
        preferences: UserPreferences,
        limit: int = 5,
    ) -> list[Activity]:
        """Return parsed activity candidates proposed by the LLM."""
        payload = self.client.generate_structured(
            system_prompt=(
                "You propose activity candidates for a weather recommendation "
                "system only after the deterministic catalog found no safe result. "
                "You do not decide what is safe. The deterministic rules will "
                "verify every candidate after your response. Prefer close indoor "
                "alternatives related to the user's requested activity. Do not "
                "include real venues, addresses, promotions, login requirements, "
                "or unavailable services. Return concise generic activities only."
            ),
            user_prompt=json.dumps(
                _build_generation_context(weather, preferences, limit),
                ensure_ascii=True,
                sort_keys=True,
            ),
            schema_name="llm_activity_candidates",
            json_schema=ACTIVITY_GENERATION_SCHEMA,
        )
        return _parse_generated_activities(payload, limit, preferences)


def _build_generation_context(
    weather: WeatherData,
    preferences: UserPreferences,
    limit: int,
) -> dict[str, Any]:
    return {
        "limit": max(1, min(limit, 5)),
        "weather": {
            "city": weather.city,
            "temperature_celsius": weather.temperature_celsius,
            "precipitation_probability_percent": (
                weather.precipitation_probability_percent
            ),
            "wind_speed_kmh": weather.wind_speed_kmh,
            "condition": weather.condition,
            "severity_level": weather.severity_level.value,
        },
        "preferences": {
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
            "max_transport_ease": preferences.max_transport_ease.value,
            "indoor_feedback_penalty": preferences.indoor_feedback_penalty,
        },
        "generation_constraints": [
            "Prefer indoor alternatives when outdoor weather is risky.",
            "Keep activity_type close to the requested activity when possible.",
            "Use conservative weather limits; deterministic rules decide final safety.",
        ],
    }


def _parse_generated_activities(
    payload: dict[str, Any],
    limit: int,
    preferences: UserPreferences,
) -> list[Activity]:
    raw_activities = payload.get("activities")
    if not isinstance(raw_activities, list):
        raise LLMServiceError(
            "LLM activity generation must return an activities list."
        )

    activities: list[Activity] = []
    seen_names: set[str] = set()

    for index, raw_activity in enumerate(raw_activities[:limit]):
        activity = _parse_generated_activity(raw_activity, index)
        _validate_activity_relevance(activity, preferences, index)
        normalized_name = activity.name.casefold()
        if normalized_name in seen_names:
            raise LLMServiceError(
                f"LLM generated a duplicate activity: {activity.name}"
            )
        seen_names.add(normalized_name)
        activities.append(activity)

    return activities


def _validate_activity_relevance(
    activity: Activity,
    preferences: UserPreferences,
    index: int,
) -> None:
    preferred_type = preferences.preferred_activity_type.casefold()
    activity_type_matches = activity.activity_type.casefold() == preferred_type
    tags_match = preferred_type in {tag.casefold() for tag in activity.tags}

    if not activity_type_matches and not tags_match:
        raise LLMServiceError(
            "LLM generated activity at index "
            f"{index} is unrelated to the requested activity."
        )


def _parse_generated_activity(raw_activity: Any, index: int) -> Activity:
    if not isinstance(raw_activity, dict):
        raise LLMServiceError(
            f"LLM generated activity at index {index} must be an object."
        )

    extra_fields = set(raw_activity) - ALLOWED_ACTIVITY_FIELDS
    if extra_fields:
        raise LLMServiceError(
            "LLM generated activity at index "
            f"{index} contains unsupported fields: "
            + ", ".join(sorted(extra_fields))
        )

    try:
        activity = Activity(
            name=_require_text(raw_activity["name"], "name", index),
            activity_type=_require_text(
                raw_activity["activity_type"],
                "activity_type",
                index,
            ),
            is_outdoor=_require_bool(raw_activity["is_outdoor"], "is_outdoor", index),
            min_temperature_celsius=float(
                raw_activity["min_temperature_celsius"]
            ),
            max_temperature_celsius=float(
                raw_activity["max_temperature_celsius"]
            ),
            max_precipitation_probability_percent=int(
                raw_activity["max_precipitation_probability_percent"]
            ),
            max_wind_speed_kmh=float(raw_activity["max_wind_speed_kmh"]),
            purpose=_require_text(raw_activity["purpose"], "purpose", index),
            intensity=_parse_enum(
                ActivityIntensity,
                raw_activity["intensity"],
                "intensity",
                index,
            ),
            duration_minutes=int(raw_activity["duration_minutes"]),
            cost_level=_parse_enum(
                CostLevel,
                raw_activity["cost_level"],
                "cost_level",
                index,
            ),
            weather_sensitivity=_parse_enum(
                WeatherSensitivity,
                raw_activity["weather_sensitivity"],
                "weather_sensitivity",
                index,
            ),
            requires_reservation=_require_bool(
                raw_activity["requires_reservation"],
                "requires_reservation",
                index,
            ),
            transport_ease=_parse_enum(
                TransportEase,
                raw_activity.get("transport_ease", "moderate"),
                "transport_ease",
                index,
            ),
            suitable_for=_parse_text_tuple(
                raw_activity["suitable_for"],
                "suitable_for",
                index,
            ),
            tags=_parse_text_tuple(raw_activity["tags"], "tags", index),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMServiceError(
            f"LLM generated activity at index {index} contains invalid data."
        ) from exc

    _validate_generated_activity(activity, index)
    return activity


def _require_text(value: Any, field_name: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid {field_name}."
        )
    return value.strip()


def _require_bool(value: Any, field_name: str, index: int) -> bool:
    if not isinstance(value, bool):
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid {field_name}."
        )
    return value


def _parse_enum(
    enum_type: type[ActivityIntensity]
    | type[CostLevel]
    | type[TransportEase]
    | type[WeatherSensitivity],
    value: Any,
    field_name: str,
    index: int,
) -> ActivityIntensity | CostLevel | TransportEase | WeatherSensitivity:
    try:
        return enum_type(str(value).strip().casefold())
    except ValueError as exc:
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid {field_name}."
        ) from exc


def _parse_text_tuple(value: Any, field_name: str, index: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid {field_name}."
        )

    items = tuple(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    )
    if len(items) != len(value):
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid {field_name}."
        )
    return items


def _validate_generated_activity(activity: Activity, index: int) -> None:
    if activity.min_temperature_celsius > activity.max_temperature_celsius:
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid temperature bounds."
        )
    if not 0 <= activity.max_precipitation_probability_percent <= 100:
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid precipitation limit."
        )
    if activity.max_wind_speed_kmh < 0:
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid wind limit."
        )
    if activity.duration_minutes <= 0:
        raise LLMServiceError(
            f"LLM generated activity at index {index} has invalid duration."
        )
