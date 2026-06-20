"""Tests for environment-based application configuration."""

import unittest

from app.config import ConfigurationError, LLMSettings, VenueProviderSettings


class LLMSettingsTests(unittest.TestCase):
    def test_llm_is_disabled_by_default_without_secrets(self) -> None:
        settings = LLMSettings.from_environment({})

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.api_key, "")

    def test_enabled_llm_requires_provider_model_and_key(self) -> None:
        with self.assertRaisesRegex(
            ConfigurationError,
            "LLM_PROVIDER, LLM_MODEL, LLM_API_KEY",
        ):
            LLMSettings.from_environment({"LLM_ENABLED": "true"})

    def test_enabled_llm_configuration_is_loaded(self) -> None:
        settings = LLMSettings.from_environment(
            {
                "LLM_ENABLED": "true",
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "configured-model",
                "LLM_API_KEY": "secret-value",
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.model, "configured-model")
        self.assertEqual(settings.api_key, "secret-value")
        self.assertNotIn("secret-value", repr(settings))

    def test_invalid_enabled_value_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "true or false"):
            LLMSettings.from_environment({"LLM_ENABLED": "sometimes"})


class VenueProviderSettingsTests(unittest.TestCase):
    def test_default_venue_provider_is_json(self) -> None:
        settings = VenueProviderSettings.from_environment({})

        self.assertEqual(settings.provider, "json")
        self.assertEqual(settings.json_path, "")

    def test_custom_json_provider_settings_are_loaded(self) -> None:
        settings = VenueProviderSettings.from_environment(
            {
                "VENUE_PROVIDER": "json",
                "VENUE_JSON_PATH": "/tmp/venues.json",
            }
        )

        self.assertEqual(settings.provider, "json")
        self.assertEqual(settings.json_path, "/tmp/venues.json")

    def test_google_places_provider_settings_are_loaded(self) -> None:
        settings = VenueProviderSettings.from_environment(
            {
                "VENUE_PROVIDER": "google_places",
                "GOOGLE_PLACES_API_KEY": "secret-value",
                "GOOGLE_PLACES_RADIUS_METERS": "1200",
                "GOOGLE_PLACES_MAX_RESULTS": "8",
                "GOOGLE_PLACES_LANGUAGE_CODE": "tr",
            }
        )

        self.assertEqual(settings.provider, "google_places")
        self.assertEqual(settings.google_places_api_key, "secret-value")
        self.assertEqual(settings.google_places_radius_meters, 1200)
        self.assertEqual(settings.google_places_max_results, 8)
        self.assertEqual(settings.google_places_language_code, "tr")
        self.assertNotIn("secret-value", repr(settings))

    def test_google_places_provider_requires_api_key(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "GOOGLE_PLACES_API_KEY"):
            VenueProviderSettings.from_environment(
                {"VENUE_PROVIDER": "google_places"}
            )

    def test_invalid_venue_provider_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "VENUE_PROVIDER"):
            VenueProviderSettings.from_environment({"VENUE_PROVIDER": "llm"})


if __name__ == "__main__":
    unittest.main()
