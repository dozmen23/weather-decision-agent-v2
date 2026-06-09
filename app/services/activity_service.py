"""Activity catalog loading and candidate retrieval."""

import json
from pathlib import Path
from typing import Any

from app.models.activity import Activity


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "activities.json"

REQUIRED_FIELDS = {
    "name",
    "activity_type",
    "is_outdoor",
    "min_temperature_celsius",
    "max_temperature_celsius",
    "max_precipitation_probability_percent",
    "max_wind_speed_kmh",
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
            )
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
    if not isinstance(value, bool):
        raise ActivityCatalogError(
            f"Activity at index {index} has a non-boolean is_outdoor value."
        )
    return value


def _validate_activity_values(activity: Activity, index: int) -> None:
    if not activity.name or not activity.activity_type:
        raise ActivityCatalogError(
            f"Activity at index {index} must have a name and activity type."
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
