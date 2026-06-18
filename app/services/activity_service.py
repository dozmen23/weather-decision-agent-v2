"""Activity catalog loading and candidate retrieval."""

import json
from pathlib import Path
from typing import Any

from app.models.activity import (
    Activity,
    ActivityIntensity,
    CostLevel,
    WeatherSensitivity,
)


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "activities.json"

REQUIRED_FIELDS = {
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
}


class ActivityCatalogError(ValueError):
    """Raised when the activity catalog cannot be loaded safely."""


class ActivityService:
    """Provide validated activity candidates from a JSON catalog."""

    def __init__(self, catalog_path: Path = DEFAULT_CATALOG_PATH) -> None:
        self.catalog_path = catalog_path

    def get_all(self) -> list[Activity]:
        """Load and return every validated activity in the catalog."""
        try:
            raw_catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ActivityCatalogError(
                f"Activity catalog was not found: {self.catalog_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ActivityCatalogError(
                f"Activity catalog contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(raw_catalog, list):
            raise ActivityCatalogError("Activity catalog must contain a JSON list.")

        activities = [
            self._parse_activity(item, index)
            for index, item in enumerate(raw_catalog)
        ]
        self._validate_unique_names(activities)
        return activities

    def find_candidates(
        self,
        activity_type: str | None = None,
        is_outdoor: bool | None = None,
    ) -> list[Activity]:
        """Return catalog entries matching the requested optional filters."""
        normalized_type = activity_type.casefold() if activity_type else None
        candidates = self.get_all()

        if normalized_type is not None:
            candidates = [
                activity
                for activity in candidates
                if activity.activity_type.casefold() == normalized_type
            ]

        if is_outdoor is not None:
            candidates = [
                activity
                for activity in candidates
                if activity.is_outdoor is is_outdoor
            ]

        return candidates

    def find_similar_candidates(
        self,
        activity_type: str,
        is_outdoor: bool | None = None,
        limit: int = 8,
    ) -> list[Activity]:
        """Return semantically related activities ordered by similarity."""
        if limit <= 0:
            return []

        normalized_type = activity_type.strip().casefold()
        activities = self.get_all()
        reference_activities = [
            activity
            for activity in activities
            if activity.activity_type.casefold() == normalized_type
        ]
        if not reference_activities:
            return []

        candidates = [
            activity
            for activity in activities
            if is_outdoor is None or activity.is_outdoor is is_outdoor
        ]
        scored_candidates = [
            (
                max(
                    _activity_similarity(reference, candidate)
                    for reference in reference_activities
                ),
                candidate,
            )
            for candidate in candidates
        ]

        return [
            candidate
            for score, candidate in sorted(
                scored_candidates,
                key=lambda item: (-item[0], item[1].name),
            )
            if score >= 25
        ][:limit]

    @staticmethod
    def _parse_activity(raw_activity: Any, index: int) -> Activity:
        if not isinstance(raw_activity, dict):
            raise ActivityCatalogError(
                f"Activity at index {index} must be a JSON object."
            )

        missing_fields = REQUIRED_FIELDS - raw_activity.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ActivityCatalogError(
                f"Activity at index {index} is missing fields: {missing}"
            )

        try:
            activity = Activity(
                name=str(raw_activity["name"]).strip(),
                activity_type=str(raw_activity["activity_type"]).strip(),
                is_outdoor=_require_boolean(raw_activity["is_outdoor"], index),
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
                purpose=str(raw_activity["purpose"]).strip(),
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
                requires_reservation=_require_boolean_field(
                    raw_activity["requires_reservation"],
                    "requires_reservation",
                    index,
                ),
                suitable_for=_parse_string_list(
                    raw_activity["suitable_for"],
                    "suitable_for",
                    index,
                ),
                tags=_parse_string_list(
                    raw_activity["tags"],
                    "tags",
                    index,
                ),
            )
        except ActivityCatalogError:
            raise
        except (TypeError, ValueError) as exc:
            raise ActivityCatalogError(
                f"Activity at index {index} contains an invalid value."
            ) from exc

        _validate_activity_values(activity, index)
        return activity

    @staticmethod
    def _validate_unique_names(activities: list[Activity]) -> None:
        normalized_names = [activity.name.casefold() for activity in activities]
        if len(normalized_names) != len(set(normalized_names)):
            raise ActivityCatalogError("Activity names must be unique.")


def _require_boolean(value: Any, index: int) -> bool:
    return _require_boolean_field(value, "is_outdoor", index)


def _require_boolean_field(
    value: Any,
    field_name: str,
    index: int,
) -> bool:
    if not isinstance(value, bool):
        raise ActivityCatalogError(
            f"Activity at index {index} has a non-boolean {field_name} value."
        )
    return value


def _parse_enum(
    enum_type: type[ActivityIntensity]
    | type[CostLevel]
    | type[WeatherSensitivity],
    value: Any,
    field_name: str,
    index: int,
) -> ActivityIntensity | CostLevel | WeatherSensitivity:
    try:
        return enum_type(str(value).strip().casefold())
    except ValueError as exc:
        allowed_values = ", ".join(item.value for item in enum_type)
        raise ActivityCatalogError(
            f"Activity at index {index} has invalid {field_name}; "
            f"expected one of: {allowed_values}."
        ) from exc


def _parse_string_list(
    value: Any,
    field_name: str,
    index: int,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ActivityCatalogError(
            f"Activity at index {index} must have a non-empty "
            f"{field_name} list."
        )

    normalized = tuple(item.strip().casefold() for item in value)
    if len(normalized) != len(set(normalized)):
        raise ActivityCatalogError(
            f"Activity at index {index} has duplicate {field_name} values."
        )
    return normalized


def _validate_activity_values(activity: Activity, index: int) -> None:
    if not activity.name or not activity.activity_type or not activity.purpose:
        raise ActivityCatalogError(
            f"Activity at index {index} must have a name, activity type, "
            "and purpose."
        )

    if activity.duration_minutes <= 0:
        raise ActivityCatalogError(
            f"Activity at index {index} has an invalid duration."
        )

    if activity.min_temperature_celsius > activity.max_temperature_celsius:
        raise ActivityCatalogError(
            f"Activity at index {index} has an invalid temperature range."
        )

    if not 0 <= activity.max_precipitation_probability_percent <= 100:
        raise ActivityCatalogError(
            f"Activity at index {index} has an invalid precipitation limit."
        )

    if activity.max_wind_speed_kmh < 0:
        raise ActivityCatalogError(
            f"Activity at index {index} has a negative wind limit."
        )


def _activity_similarity(reference: Activity, candidate: Activity) -> int:
    score = 0

    if reference.activity_type.casefold() == candidate.activity_type.casefold():
        score += 100
    if reference.purpose.casefold() == candidate.purpose.casefold():
        score += 35

    shared_tags = set(reference.tags) & set(candidate.tags)
    score += min(len(shared_tags), 4) * 10

    if reference.intensity is candidate.intensity:
        score += 10

    return score
