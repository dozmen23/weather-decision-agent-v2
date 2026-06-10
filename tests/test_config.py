"""Tests for environment-based application configuration."""

import unittest

from app.config import ConfigurationError, LLMSettings


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


if __name__ == "__main__":
    unittest.main()
