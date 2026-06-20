"""In-memory venue provider for tests and controlled demos."""

from app.models.venue import Venue
from app.services.venue_providers.json_provider import validate_unique_venue_names


class StaticVenueProvider:
    """Return pre-validated venues from memory."""

    def __init__(self, venues: list[Venue]) -> None:
        validate_unique_venue_names(venues)
        self._venues = list(venues)

    def get_all(self) -> list[Venue]:
        """Return the configured static venues."""
        return list(self._venues)
