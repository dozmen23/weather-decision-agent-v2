"""Tests for venue provider boundaries."""

import unittest

from app.models.activity import CostLevel, TransportEase
from app.models.venue import Venue
from app.services.venue_service import VenueCatalogError
from app.services.venue_providers import (
    ExternalVenueProvider,
    StaticVenueProvider,
)


class FakeExternalVenueClient:
    def __init__(self, payload):
        self.payload = payload

    def fetch_venues(self):
        return self.payload


class FailingExternalVenueClient:
    def fetch_venues(self):
        raise RuntimeError("rate limited")


class VenueProviderTests(unittest.TestCase):
    def test_external_provider_validates_structured_payload(self) -> None:
        provider = ExternalVenueProvider(
            FakeExternalVenueClient(
                [
                    {
                        "name": "Live Indoor Walk",
                        "activity_types": ["walking"],
                        "is_outdoor": False,
                        "city": "Istanbul",
                        "latitude": 41.01,
                        "longitude": 29.02,
                        "distance_km": 1.2,
                        "transport_ease": "easy",
                        "cost_level": "free",
                        "requires_reservation": False,
                        "source": "external-test",
                        "tags": ["indoor", "walking"],
                    }
                ]
            )
        )

        venues = provider.get_all()

        self.assertEqual(venues[0].name, "Live Indoor Walk")
        self.assertEqual(venues[0].source, "external-test")

    def test_external_provider_rejects_incomplete_payload(self) -> None:
        provider = ExternalVenueProvider(
            FakeExternalVenueClient([{"name": "Incomplete Live Venue"}])
        )

        with self.assertRaisesRegex(VenueCatalogError, "missing fields"):
            provider.get_all()

    def test_external_provider_wraps_client_errors(self) -> None:
        provider = ExternalVenueProvider(FailingExternalVenueClient())

        with self.assertRaisesRegex(VenueCatalogError, "could not fetch"):
            provider.get_all()

    def test_external_provider_rejects_non_list_payload(self) -> None:
        provider = ExternalVenueProvider(
            FakeExternalVenueClient({"venues": []})
        )

        with self.assertRaisesRegex(VenueCatalogError, "venue list"):
            provider.get_all()

    def test_static_provider_rejects_duplicate_names(self) -> None:
        venue = Venue(
            name="Duplicate Venue",
            activity_types=("walking",),
            is_outdoor=False,
            city="Istanbul",
            latitude=41.0,
            longitude=29.0,
            distance_km=1.0,
            transport_ease=TransportEase.EASY,
            cost_level=CostLevel.FREE,
            requires_reservation=False,
            source="test",
        )

        with self.assertRaisesRegex(VenueCatalogError, "unique"):
            StaticVenueProvider([venue, venue])


if __name__ == "__main__":
    unittest.main()
