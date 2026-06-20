"""External venue provider adapter boundary.

Concrete clients such as Google Places or Foursquare should fetch data and
normalize it into the structured venue payload accepted here. The provider then
validates the payload before the recommendation system can use it.
"""

from typing import Any, Protocol

from app.models.venue import Venue
from app.services.venue_providers.json_provider import (
    VenueCatalogError,
    parse_venue_payload,
    validate_unique_venue_names,
)


class ExternalVenueClient(Protocol):
    """Client boundary for a live places data source."""

    def fetch_venues(self) -> list[dict[str, Any]]:
        """Return structured venue payloads from the external source."""


class ExternalVenueProvider:
    """Load venues through a live client and validate them deterministically."""

    def __init__(self, client: ExternalVenueClient) -> None:
        self.client = client

    def get_all(self) -> list[Venue]:
        """Fetch, parse, and validate venues from the external client."""
        try:
            raw_venues = self.client.fetch_venues()
        except Exception as exc:
            raise VenueCatalogError(
                "External venue provider could not fetch venues."
            ) from exc

        if not isinstance(raw_venues, list):
            raise VenueCatalogError(
                "External venue provider must return a venue list."
            )

        venues = [
            parse_venue_payload(raw_venue, index)
            for index, raw_venue in enumerate(raw_venues)
        ]
        validate_unique_venue_names(venues)
        return venues
