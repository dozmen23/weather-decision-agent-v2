"""JSON-backed trusted venue provider."""

import json
from pathlib import Path
from typing import Any

from app.models.activity import CostLevel, TransportEase
from app.models.venue import Venue


DEFAULT_VENUE_PATH = Path(__file__).resolve().parents[3] / "data" / "venues.json"

REQUIRED_VENUE_FIELDS = {
    "name",
    "activity_types",
    "is_outdoor",
    "city",
    "latitude",
    "longitude",
    "distance_km",
    "transport_ease",
    "cost_level",
    "requires_reservation",
    "source",
    "tags",
}


class VenueCatalogError(ValueError):
    """Raised when venue data cannot be loaded safely."""


class JsonVenueProvider:
    """Load trusted venue candidates from a local JSON catalog."""

    def __init__(self, venue_path: Path = DEFAULT_VENUE_PATH) -> None:
        self.venue_path = venue_path

    def get_all(self) -> list[Venue]:
        """Load and return every validated venue in the catalog."""
        try:
            raw_catalog = json.loads(self.venue_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VenueCatalogError(
                f"Venue catalog was not found: {self.venue_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise VenueCatalogError(
                f"Venue catalog contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(raw_catalog, list):
            raise VenueCatalogError("Venue catalog must contain a JSON list.")

        venues = [
            parse_venue_payload(item, index)
            for index, item in enumerate(raw_catalog)
        ]
        validate_unique_venue_names(venues)
        return venues


def parse_venue_payload(raw_venue: Any, index: int) -> Venue:
    """Parse and validate one structured venue payload."""
    if not isinstance(raw_venue, dict):
        raise VenueCatalogError(
            f"Venue at index {index} must be a JSON object."
        )

    missing_fields = REQUIRED_VENUE_FIELDS - raw_venue.keys()
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise VenueCatalogError(
            f"Venue at index {index} is missing fields: {missing}"
        )

    try:
        venue = Venue(
            name=str(raw_venue["name"]).strip(),
            activity_types=_parse_text_tuple(
                raw_venue["activity_types"],
                "activity_types",
                index,
            ),
            is_outdoor=_require_bool(raw_venue["is_outdoor"], index),
            city=str(raw_venue["city"]).strip(),
            latitude=float(raw_venue["latitude"]),
            longitude=float(raw_venue["longitude"]),
            distance_km=float(raw_venue["distance_km"]),
            transport_ease=TransportEase(
                str(raw_venue["transport_ease"]).strip().casefold()
            ),
            cost_level=CostLevel(
                str(raw_venue["cost_level"]).strip().casefold()
            ),
            requires_reservation=_require_bool(
                raw_venue["requires_reservation"],
                index,
            ),
            source=str(raw_venue["source"]).strip(),
            tags=_parse_text_tuple(raw_venue["tags"], "tags", index),
        )
    except (TypeError, ValueError) as exc:
        raise VenueCatalogError(
            f"Venue at index {index} contains an invalid value."
        ) from exc

    _validate_venue_values(venue, index)
    return venue


def _require_bool(value: Any, index: int) -> bool:
    if not isinstance(value, bool):
        raise VenueCatalogError(f"Venue at index {index} has invalid boolean data.")
    return value


def _parse_text_tuple(value: Any, field_name: str, index: int) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise VenueCatalogError(
            f"Venue at index {index} must have a non-empty {field_name} list."
        )

    normalized = tuple(item.strip().casefold() for item in value)
    if len(normalized) != len(set(normalized)):
        raise VenueCatalogError(
            f"Venue at index {index} has duplicate {field_name} values."
        )
    return normalized


def _validate_venue_values(venue: Venue, index: int) -> None:
    if not venue.name or not venue.city or not venue.source:
        raise VenueCatalogError(
            f"Venue at index {index} must have a name, city, and source."
        )
    if not -90 <= venue.latitude <= 90:
        raise VenueCatalogError(f"Venue at index {index} has invalid latitude.")
    if not -180 <= venue.longitude <= 180:
        raise VenueCatalogError(f"Venue at index {index} has invalid longitude.")
    if venue.distance_km < 0:
        raise VenueCatalogError(f"Venue at index {index} has invalid distance.")


def validate_unique_venue_names(venues: list[Venue]) -> None:
    """Reject duplicate venue names from a trusted provider payload."""
    normalized_names = [venue.name.casefold() for venue in venues]
    if len(normalized_names) != len(set(normalized_names)):
        raise VenueCatalogError("Venue names must be unique.")
