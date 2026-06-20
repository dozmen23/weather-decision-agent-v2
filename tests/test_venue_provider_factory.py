"""Tests for venue provider factory configuration."""

import json
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigurationError, VenueProviderSettings
from app.services.venue_provider_factory import (
    create_venue_provider,
    create_venue_provider_from_environment,
    inspect_venue_provider,
)
from app.services.venue_providers import (
    ExternalVenueProvider,
    GooglePlacesVenueProvider,
    JsonVenueProvider,
)


class FakeExternalVenueClient:
    def fetch_venues(self):
        return []


class VenueProviderFactoryTests(unittest.TestCase):
    def test_json_provider_is_default(self) -> None:
        provider = create_venue_provider_from_environment({})

        self.assertIsInstance(provider, JsonVenueProvider)

    def test_json_provider_accepts_custom_catalog_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            venue_path = Path(temporary_directory) / "venues.json"
            venue_path.write_text(json.dumps([]), encoding="utf-8")

            provider = create_venue_provider_from_environment(
                {
                    "VENUE_PROVIDER": "json",
                    "VENUE_JSON_PATH": str(venue_path),
                }
            )

            self.assertIsInstance(provider, JsonVenueProvider)
            self.assertEqual(provider.venue_path, venue_path)

    def test_external_provider_requires_client(self) -> None:
        settings = VenueProviderSettings(provider="external")

        with self.assertRaisesRegex(ConfigurationError, "external venue client"):
            create_venue_provider(settings)

    def test_external_provider_can_be_created_with_client(self) -> None:
        provider = create_venue_provider(
            VenueProviderSettings(provider="external"),
            external_client=FakeExternalVenueClient(),
        )

        self.assertIsInstance(provider, ExternalVenueProvider)

    def test_google_places_provider_can_be_created_with_key(self) -> None:
        provider = create_venue_provider(
            VenueProviderSettings(
                provider="google_places",
                google_places_api_key="secret-value",
            )
        )

        self.assertIsInstance(provider, GooglePlacesVenueProvider)

    def test_provider_inspection_reports_available_json_provider(self) -> None:
        inspection = inspect_venue_provider({})

        self.assertTrue(inspection.available)
        self.assertEqual(inspection.provider, "json")
        self.assertGreater(inspection.venue_count, 0)
        self.assertIn("demo", inspection.sources)

    def test_provider_inspection_reports_configuration_error(self) -> None:
        inspection = inspect_venue_provider({"VENUE_PROVIDER": "external"})

        self.assertFalse(inspection.available)
        self.assertEqual(inspection.provider, "external")
        self.assertIn("external venue client", inspection.error)

    def test_provider_inspection_reports_available_external_provider(self) -> None:
        inspection = inspect_venue_provider(
            {"VENUE_PROVIDER": "external"},
            external_client=FakeExternalVenueClient(),
        )

        self.assertTrue(inspection.available)
        self.assertEqual(inspection.provider, "external")
        self.assertEqual(inspection.venue_count, 0)
        self.assertEqual(inspection.sources, ())

    def test_provider_inspection_reports_available_google_places_provider(self) -> None:
        inspection = inspect_venue_provider(
            {
                "VENUE_PROVIDER": "google_places",
                "GOOGLE_PLACES_API_KEY": "secret-value",
            }
        )

        self.assertTrue(inspection.available)
        self.assertEqual(inspection.provider, "google_places")
        self.assertEqual(inspection.venue_count, 0)
        self.assertEqual(inspection.sources, ("google_places",))

    def test_provider_inspection_reports_invalid_provider_setting(self) -> None:
        inspection = inspect_venue_provider({"VENUE_PROVIDER": "llm"})

        self.assertFalse(inspection.available)
        self.assertEqual(inspection.provider, "llm")
        self.assertIn("VENUE_PROVIDER", inspection.error)


if __name__ == "__main__":
    unittest.main()
