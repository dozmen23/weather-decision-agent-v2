"""Tests for the defensive reverse geocoding service."""

import unittest

from app.services.geocoding_service import reverse_geocode_label


class ReverseGeocodeTests(unittest.TestCase):
    def test_builds_district_and_city_label(self) -> None:
        payload = {
            "locality": "Caddebostan",
            "city": "İstanbul",
            "principalSubdivision": "İstanbul",
        }

        label = reverse_geocode_label(
            40.96,
            29.06,
            json_fetcher=lambda _url: payload,
        )

        self.assertEqual(label, "Caddebostan, İstanbul")

    def test_avoids_duplicate_context(self) -> None:
        payload = {
            "locality": "İstanbul",
            "city": "İstanbul",
            "principalSubdivision": "İstanbul",
        }

        label = reverse_geocode_label(
            41.0,
            29.0,
            json_fetcher=lambda _url: payload,
        )

        self.assertEqual(label, "İstanbul")

    def test_falls_back_to_city_when_no_locality(self) -> None:
        payload = {
            "locality": "",
            "city": "Ankara",
            "principalSubdivision": "Ankara",
        }

        label = reverse_geocode_label(
            39.93,
            32.86,
            json_fetcher=lambda _url: payload,
        )

        self.assertEqual(label, "Ankara")

    def test_network_failure_returns_none(self) -> None:
        def failing_fetcher(_url: str):
            raise OSError("network down")

        self.assertIsNone(
            reverse_geocode_label(40.0, 29.0, json_fetcher=failing_fetcher)
        )

    def test_invalid_coordinates_return_none(self) -> None:
        self.assertIsNone(
            reverse_geocode_label(
                200.0,
                29.0,
                json_fetcher=lambda _url: {"city": "Nowhere"},
            )
        )

    def test_empty_payload_returns_none(self) -> None:
        self.assertIsNone(
            reverse_geocode_label(40.0, 29.0, json_fetcher=lambda _url: {})
        )


if __name__ == "__main__":
    unittest.main()
