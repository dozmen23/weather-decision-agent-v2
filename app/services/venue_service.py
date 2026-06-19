"""Trusted venue catalog loading and filtering."""

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.models.activity import CostLevel, TransportEase
from app.models.user_preferences import UserPreferences
from app.models.venue import Venue, VenueFilterTrace


DEFAULT_VENUE_PATH = Path(__file__).resolve().parents[2] / "data" / "venues.json"

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


class VenueService:
    """Return verified venue candidates from a trusted structured catalog."""

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
            self._parse_venue(item, index)
            for index, item in enumerate(raw_catalog)
        ]
        self._validate_unique_names(venues)
        return venues

    def find_candidates(
        self,
        *,
        activity_type: str,
        is_outdoor: bool,
        preferences: UserPreferences,
        origin_latitude: float | None = None,
        origin_longitude: float | None = None,
        limit: int = 2,
    ) -> list[Venue]:
        """Return filtered venues for a verified activity recommendation."""
        if limit <= 0:
            return []

        candidates, _ = self.find_candidates_with_trace(
            activity_type=activity_type,
            is_outdoor=is_outdoor,
            preferences=preferences,
            origin_latitude=origin_latitude,
            origin_longitude=origin_longitude,
            limit=limit,
        )
        return candidates

    def find_candidates_with_trace(
        self,
        *,
        activity_type: str,
        is_outdoor: bool,
        preferences: UserPreferences,
        origin_latitude: float | None = None,
        origin_longitude: float | None = None,
        limit: int = 2,
    ) -> tuple[list[Venue], list[VenueFilterTrace]]:
        """Return filtered venues and developer-facing filter trace."""
        if limit <= 0:
            return [], []

        normalized_type = activity_type.casefold()
        venues = _with_origin_distances(
            self.get_all(),
            origin_latitude,
            origin_longitude,
        )
        candidates = []
        traces = []
        for venue in venues:
            reasons = _venue_filter_reasons(
                venue,
                normalized_type,
                is_outdoor,
                preferences,
            )
            passed = not reasons
            if passed:
                candidates.append(venue)
            traces.append(
                VenueFilterTrace(
                    venue_name=venue.name,
                    passed=passed,
                    reasons=reasons or ("Mekan tüm filtreleri geçti.",),
                    distance_km=venue.distance_km,
                )
            )

        ranked_candidates = sorted(
            candidates,
            key=lambda venue: (
                _transport_rank(venue.transport_ease),
                venue.distance_km,
                venue.name,
            ),
        )
        return ranked_candidates[:limit], traces

    @staticmethod
    def _parse_venue(raw_venue: Any, index: int) -> Venue:
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

    @staticmethod
    def _validate_unique_names(venues: list[Venue]) -> None:
        normalized_names = [venue.name.casefold() for venue in venues]
        if len(normalized_names) != len(set(normalized_names)):
            raise VenueCatalogError("Venue names must be unique.")


def _venue_matches_preferences(
    venue: Venue,
    preferences: UserPreferences,
) -> bool:
    return not _preference_filter_reasons(venue, preferences)


def _venue_filter_reasons(
    venue: Venue,
    normalized_activity_type: str,
    is_outdoor: bool,
    preferences: UserPreferences,
) -> tuple[str, ...]:
    reasons = []
    if normalized_activity_type not in venue.activity_types:
        reasons.append("Aktivite türü eşleşmedi.")
    if venue.is_outdoor is not is_outdoor:
        reasons.append("Açık/kapalı alan tipi eşleşmedi.")
    reasons.extend(_preference_filter_reasons(venue, preferences))
    return tuple(reasons)


def _preference_filter_reasons(
    venue: Venue,
    preferences: UserPreferences,
) -> tuple[str, ...]:
    reasons = []
    if _cost_rank(venue.cost_level) > _cost_rank(preferences.max_cost_level):
        reasons.append("Bütçe sınırını aştı.")
    if preferences.avoid_reservations and venue.requires_reservation:
        reasons.append("Rezervasyon istemiyorum tercihine uymadı.")
    if _transport_rank(venue.transport_ease) > _transport_rank(
        preferences.max_transport_ease
    ):
        reasons.append("Ulaşım kolaylığı sınırını aştı.")
    return tuple(reasons)


def _with_origin_distances(
    venues: list[Venue],
    origin_latitude: float | None,
    origin_longitude: float | None,
) -> list[Venue]:
    if origin_latitude is None or origin_longitude is None:
        return venues

    _validate_origin(origin_latitude, origin_longitude)
    return [
        replace(
            venue,
            distance_km=_distance_km_between(
                origin_latitude,
                origin_longitude,
                venue.latitude,
                venue.longitude,
            ),
        )
        for venue in venues
    ]


def _validate_origin(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise VenueCatalogError("Origin latitude is invalid.")
    if not -180 <= longitude <= 180:
        raise VenueCatalogError("Origin longitude is invalid.")


def _distance_km_between(
    origin_latitude: float,
    origin_longitude: float,
    venue_latitude: float,
    venue_longitude: float,
) -> float:
    earth_radius_km = 6371.0
    origin_latitude_rad = math.radians(origin_latitude)
    venue_latitude_rad = math.radians(venue_latitude)
    latitude_delta = math.radians(venue_latitude - origin_latitude)
    longitude_delta = math.radians(venue_longitude - origin_longitude)

    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(origin_latitude_rad)
        * math.cos(venue_latitude_rad)
        * math.sin(longitude_delta / 2) ** 2
    )
    central_angle = 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(1 - haversine),
    )
    return round(earth_radius_km * central_angle, 1)


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


def _cost_rank(cost_level: CostLevel) -> int:
    return {
        CostLevel.FREE: 0,
        CostLevel.LOW: 1,
        CostLevel.MEDIUM: 2,
        CostLevel.HIGH: 3,
    }[cost_level]


def _transport_rank(transport_ease: TransportEase) -> int:
    return {
        TransportEase.EASY: 0,
        TransportEase.MODERATE: 1,
        TransportEase.HARD: 2,
    }[transport_ease]
