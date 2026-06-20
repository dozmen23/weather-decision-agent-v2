"""Venue candidate model for controlled real-place recommendations."""

from dataclasses import dataclass, field

from app.models.activity import CostLevel, TransportEase


@dataclass(frozen=True)
class VenueAttribution:
    """Third-party attribution returned by a trusted venue provider."""

    provider: str
    provider_uri: str = ""


@dataclass(frozen=True)
class Venue:
    """Trusted venue candidate from a structured source."""

    name: str
    activity_types: tuple[str, ...]
    is_outdoor: bool
    city: str
    latitude: float
    longitude: float
    distance_km: float
    transport_ease: TransportEase
    cost_level: CostLevel
    requires_reservation: bool
    source: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    provider_venue_id: str = ""
    google_maps_uri: str = ""
    attributions: tuple[VenueAttribution, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VenueFilterTrace:
    """Developer-facing trace entry for venue candidate filtering."""

    venue_name: str
    passed: bool
    reasons: tuple[str, ...]
    distance_km: float
