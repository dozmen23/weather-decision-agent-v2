"""Tests for Google Places venue normalization."""

import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from app.models.activity import CostLevel, TransportEase
from app.services.venue_providers.google_places_provider import (
    PLACE_TYPES_BY_ACTIVITY,
    GooglePlacesClient,
    GooglePlacesVenueProvider,
    google_place_types_for_activity,
)
from app.services.venue_service import VenueCatalogError


class FakeGooglePlacesClient:
    def __init__(self, places):
        self.places = places
        self.calls = []

    def fetch_nearby_places(
        self,
        *,
        included_types,
        latitude,
        longitude,
        radius_meters,
        max_result_count,
    ):
        self.calls.append(
            {
                "included_types": included_types,
                "latitude": latitude,
                "longitude": longitude,
                "radius_meters": radius_meters,
                "max_result_count": max_result_count,
            }
        )
        return self.places


class GooglePlacesProviderTests(unittest.TestCase):
    def test_google_places_response_is_normalized_to_venues(self) -> None:
        client = FakeGooglePlacesClient(
            [
                {
                    "id": "place-1",
                    "displayName": {"text": "Yakın Park"},
                    "location": {"latitude": 41.0009, "longitude": 29.0},
                    "types": ["park", "point_of_interest"],
                    "priceLevel": "PRICE_LEVEL_FREE",
                    "businessStatus": "OPERATIONAL",
                }
            ]
        )
        provider = GooglePlacesVenueProvider(
            client,
            radius_meters=1200,
            max_result_count=7,
        )

        venues = provider.find_nearby(
            activity_type="walking",
            is_outdoor=True,
            origin_latitude=41.0,
            origin_longitude=29.0,
            limit=2,
        )

        self.assertEqual(client.calls[0]["included_types"][0], "park")
        self.assertEqual(client.calls[0]["radius_meters"], 1200)
        self.assertEqual(client.calls[0]["max_result_count"], 7)
        self.assertEqual(venues[0].name, "Yakın Park")
        self.assertEqual(venues[0].activity_types, ("walking",))
        self.assertTrue(venues[0].is_outdoor)
        self.assertEqual(venues[0].source, "google_places")
        self.assertEqual(venues[0].cost_level, CostLevel.FREE)
        self.assertEqual(venues[0].transport_ease, TransportEase.EASY)

    def test_permanently_closed_places_are_skipped(self) -> None:
        provider = GooglePlacesVenueProvider(
            FakeGooglePlacesClient(
                [
                    {
                        "displayName": {"text": "Kapalı Salon"},
                        "location": {"latitude": 41.0, "longitude": 29.0},
                        "types": ["gym"],
                        "businessStatus": "CLOSED_PERMANENTLY",
                    }
                ]
            )
        )

        venues = provider.find_nearby(
            activity_type="running",
            is_outdoor=False,
            origin_latitude=41.0,
            origin_longitude=29.0,
            limit=2,
        )

        self.assertEqual(venues, [])

    def test_activity_type_mapping_uses_indoor_and_outdoor_sets(self) -> None:
        self.assertIn("park", google_place_types_for_activity("walking", True))
        self.assertIn(
            "shopping_mall",
            google_place_types_for_activity("walking", False),
        )

        for activity_type in PLACE_TYPES_BY_ACTIVITY:
            self.assertTrue(google_place_types_for_activity(activity_type, True))
            self.assertTrue(google_place_types_for_activity(activity_type, False))

    def test_unknown_activity_uses_safe_setting_specific_place_types(self) -> None:
        outdoor_types = google_place_types_for_activity("unknown", True)
        indoor_types = google_place_types_for_activity("unknown", False)

        self.assertIn("park", outdoor_types)
        self.assertIn("museum", indoor_types)
        self.assertNotEqual(outdoor_types, indoor_types)

    def test_malformed_place_does_not_hide_other_valid_results(self) -> None:
        provider = GooglePlacesVenueProvider(
            FakeGooglePlacesClient(
                [
                    {
                        "id": "broken",
                        "displayName": {"text": "Konumsuz Mekan"},
                        "types": ["park"],
                    },
                    {
                        "id": "valid",
                        "displayName": {"text": "Geçerli Park"},
                        "location": {"latitude": 41.001, "longitude": 29.0},
                        "types": ["park"],
                        "businessStatus": "OPERATIONAL",
                    },
                ]
            )
        )

        venues = provider.find_nearby(
            activity_type="walking",
            is_outdoor=True,
            origin_latitude=41.0,
            origin_longitude=29.0,
            limit=2,
        )

        self.assertEqual([venue.name for venue in venues], ["Geçerli Park"])

    def test_google_quota_error_keeps_provider_specific_message(self) -> None:
        error = HTTPError(
            url="https://places.googleapis.com/v1/places:searchNearby",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=BytesIO(b'{"error":{"message":"Quota exceeded"}}'),
        )

        with patch(
            "app.services.venue_providers.google_places_provider.urlopen",
            side_effect=error,
        ):
            with self.assertRaisesRegex(VenueCatalogError, "Quota exceeded"):
                GooglePlacesClient("secret").fetch_nearby_places(
                    included_types=("park",),
                    latitude=41.0,
                    longitude=29.0,
                    radius_meters=1200,
                    max_result_count=5,
                )


if __name__ == "__main__":
    unittest.main()
