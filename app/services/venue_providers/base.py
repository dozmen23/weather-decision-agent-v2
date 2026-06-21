"""Venue provider boundary for trusted place sources."""

from typing import Protocol, runtime_checkable

from app.models.venue import Venue


class VenueProvider(Protocol):
    """Load verified venue candidates from a trusted source."""

    def get_all(self) -> list[Venue]:
        """Return every venue exposed by the provider."""


@runtime_checkable
class NearbyVenueProvider(VenueProvider, Protocol):
    """Search for verified venues around a selected coordinate."""

    def find_nearby(
        self,
        *,
        activity_type: str,
        activity_name: str | None,
        is_outdoor: bool,
        origin_latitude: float,
        origin_longitude: float,
        limit: int,
    ) -> list[Venue]:
        """Return nearby venues for one verified activity recommendation."""
