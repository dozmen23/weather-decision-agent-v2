"""Trusted venue filtering over pluggable providers."""

import math
from dataclasses import replace
from pathlib import Path

from app.models.activity import CostLevel, TransportEase
from app.models.user_preferences import UserPreferences
from app.models.venue import Venue, VenueFilterTrace
from app.services.venue_providers import JsonVenueProvider, VenueProvider
from app.services.venue_providers.base import NearbyVenueProvider
from app.services.venue_providers.json_provider import (
    DEFAULT_VENUE_PATH,
    VenueCatalogError,
)


class VenueService:
    """Return verified venue candidates from a trusted provider."""

    def __init__(
        self,
        venue_path: Path = DEFAULT_VENUE_PATH,
        provider: VenueProvider | None = None,
    ) -> None:
        self.provider = provider or JsonVenueProvider(venue_path)

    def get_all(self) -> list[Venue]:
        """Return every venue exposed by the configured provider."""
        return self.provider.get_all()

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
        venues = _candidate_venues(
            self.provider,
            activity_type=activity_type,
            is_outdoor=is_outdoor,
            origin_latitude=origin_latitude,
            origin_longitude=origin_longitude,
            limit=max(limit * 4, limit),
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


def _candidate_venues(
    provider: VenueProvider,
    *,
    activity_type: str,
    is_outdoor: bool,
    origin_latitude: float | None,
    origin_longitude: float | None,
    limit: int,
) -> list[Venue]:
    if (
        origin_latitude is not None
        and origin_longitude is not None
        and isinstance(provider, NearbyVenueProvider)
    ):
        _validate_origin(origin_latitude, origin_longitude)
        return provider.find_nearby(
            activity_type=activity_type,
            is_outdoor=is_outdoor,
            origin_latitude=origin_latitude,
            origin_longitude=origin_longitude,
            limit=limit,
        )

    return _with_origin_distances(
        provider.get_all(),
        origin_latitude,
        origin_longitude,
    )


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
