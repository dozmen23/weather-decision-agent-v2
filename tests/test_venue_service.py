"""Tests for trusted venue candidate filtering."""

import json
import tempfile
import unittest
from pathlib import Path

from app.models.activity import CostLevel, TransportEase
from app.models.user_preferences import UserPreferences
from app.models.venue import Venue
from app.services.venue_service import VenueCatalogError, VenueService


class FakeVenueProvider:
    def get_all(self) -> list[Venue]:
        return [
            Venue(
                name="Provider Indoor Walk",
                activity_types=("walking",),
                is_outdoor=False,
                city="Istanbul",
                latitude=41.0,
                longitude=29.0,
                distance_km=1.5,
                transport_ease=TransportEase.EASY,
                cost_level=CostLevel.FREE,
                requires_reservation=False,
                source="fake-provider",
            )
        ]


class FakeNearbyVenueProvider:
    def __init__(self) -> None:
        self.calls = []

    def get_all(self) -> list[Venue]:
        return []

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
        self.calls.append(
            {
                "activity_type": activity_type,
                "activity_name": activity_name,
                "is_outdoor": is_outdoor,
                "origin_latitude": origin_latitude,
                "origin_longitude": origin_longitude,
                "limit": limit,
            }
        )
        return [
            Venue(
                name="Live Park Walk",
                activity_types=("walking",),
                is_outdoor=True,
                city="Istanbul",
                latitude=41.0,
                longitude=29.0,
                distance_km=0.3,
                transport_ease=TransportEase.EASY,
                cost_level=CostLevel.FREE,
                requires_reservation=False,
                source="google_places",
            )
        ]


class VenueServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preferences = UserPreferences(
            preferred_activity_type="walking",
            prefers_outdoor=False,
            min_temperature_celsius=10,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
            max_cost_level=CostLevel.LOW,
            max_transport_ease=TransportEase.EASY,
        )

    def test_default_catalog_loads_and_filters_candidates(self) -> None:
        venues = VenueService().find_candidates(
            activity_type="walking",
            is_outdoor=False,
            preferences=self.preferences,
            limit=2,
        )

        self.assertEqual(
            [venue.name for venue in venues],
            ["Demo AVM Yürüyüş Rotası", "Demo Kapalı Atletizm Pisti"],
        )
        self.assertTrue(all(not venue.is_outdoor for venue in venues))
        self.assertTrue(
            all(venue.transport_ease is TransportEase.EASY for venue in venues)
        )

    def test_service_can_use_injected_provider(self) -> None:
        venues = VenueService(provider=FakeVenueProvider()).find_candidates(
            activity_type="walking",
            is_outdoor=False,
            preferences=self.preferences,
        )

        self.assertEqual([venue.name for venue in venues], ["Provider Indoor Walk"])
        self.assertEqual(venues[0].source, "fake-provider")

    def test_nearby_provider_uses_selected_origin(self) -> None:
        provider = FakeNearbyVenueProvider()
        preferences = UserPreferences(
            preferred_activity_type="walking",
            prefers_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )

        venues = VenueService(provider=provider).find_candidates(
            activity_type="walking",
            activity_name="Park Walk",
            is_outdoor=True,
            preferences=preferences,
            origin_latitude=41.0,
            origin_longitude=29.0,
            limit=2,
        )

        self.assertEqual([venue.name for venue in venues], ["Live Park Walk"])
        self.assertEqual(provider.calls[0]["origin_latitude"], 41.0)
        self.assertEqual(provider.calls[0]["activity_name"], "Park Walk")
        self.assertEqual(provider.calls[0]["limit"], 8)

    def test_reservation_preference_filters_venues(self) -> None:
        preferences = UserPreferences(
            preferred_activity_type="sports",
            prefers_outdoor=False,
            min_temperature_celsius=10,
            max_temperature_celsius=30,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
            avoid_reservations=True,
        )

        venues = VenueService().find_candidates(
            activity_type="sports",
            is_outdoor=False,
            preferences=preferences,
        )

        self.assertEqual(venues, [])

    def test_filter_trace_explains_passed_and_rejected_venues(self) -> None:
        venues, trace = VenueService().find_candidates_with_trace(
            activity_type="walking",
            is_outdoor=False,
            preferences=self.preferences,
            limit=2,
        )

        self.assertEqual(len(venues), 2)
        passed = [item for item in trace if item.passed]
        rejected = [item for item in trace if not item.passed]
        self.assertGreaterEqual(len(passed), 2)
        self.assertTrue(
            any("Mekan tüm filtreleri geçti." in item.reasons for item in passed)
        )
        self.assertTrue(
            any(
                "Açık/kapalı alan tipi eşleşmedi." in item.reasons
                for item in rejected
            )
        )

    def test_origin_coordinates_recalculate_distances(self) -> None:
        venues = VenueService().find_candidates(
            activity_type="walking",
            is_outdoor=False,
            preferences=self.preferences,
            origin_latitude=41.0632,
            origin_longitude=29.0123,
            limit=2,
        )

        self.assertEqual(venues[0].name, "Demo AVM Yürüyüş Rotası")
        self.assertEqual(venues[0].distance_km, 0.0)
        self.assertGreater(venues[1].distance_km, venues[0].distance_km)

    def test_invalid_origin_coordinates_are_rejected(self) -> None:
        with self.assertRaisesRegex(VenueCatalogError, "Origin latitude"):
            VenueService().find_candidates(
                activity_type="walking",
                is_outdoor=False,
                preferences=self.preferences,
                origin_latitude=120,
                origin_longitude=29.0123,
            )

    def test_invalid_catalog_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            venue_path = Path(temporary_directory) / "venues.json"
            venue_path.write_text(
                json.dumps([{"name": "Incomplete"}]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(VenueCatalogError, "missing fields"):
                VenueService(venue_path).get_all()


if __name__ == "__main__":
    unittest.main()
