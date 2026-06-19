"""Tests for trusted venue candidate filtering."""

import json
import tempfile
import unittest
from pathlib import Path

from app.models.activity import CostLevel, TransportEase
from app.models.user_preferences import UserPreferences
from app.services.venue_service import VenueCatalogError, VenueService


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
