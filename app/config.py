"""Environment-based application configuration."""

import os
from dataclasses import dataclass, field
from typing import Mapping


class ConfigurationError(ValueError):
    """Raised when required application settings are invalid or missing."""


@dataclass(frozen=True)
class LLMSettings:
    """Runtime configuration for an optional LLM provider adapter."""

    enabled: bool = False
    provider: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "LLMSettings":
        """Load and validate LLM settings from environment variables."""
        source = environment if environment is not None else os.environ
        enabled = _parse_boolean(source.get("LLM_ENABLED", "false"))
        provider = source.get("LLM_PROVIDER", "").strip()
        model = source.get("LLM_MODEL", "").strip()
        api_key = source.get("LLM_API_KEY", "").strip()

        if enabled:
            missing = [
                name
                for name, value in (
                    ("LLM_PROVIDER", provider),
                    ("LLM_MODEL", model),
                    ("LLM_API_KEY", api_key),
                )
                if not value
            ]
            if missing:
                raise ConfigurationError(
                    "Enabled LLM configuration is missing: "
                    + ", ".join(missing)
                )

        return cls(
            enabled=enabled,
            provider=provider,
            model=model,
            api_key=api_key,
        )


@dataclass(frozen=True)
class VenueProviderSettings:
    """Runtime configuration for the trusted venue provider."""

    provider: str = "json"
    json_path: str = ""
    google_places_api_key: str = field(default="", repr=False)
    google_places_radius_meters: int = 2500
    google_places_max_results: int = 10
    google_places_language_code: str = "tr"

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "VenueProviderSettings":
        """Load venue provider settings from environment variables."""
        source = environment if environment is not None else os.environ
        provider = source.get("VENUE_PROVIDER", "json").strip().casefold()
        json_path = source.get("VENUE_JSON_PATH", "").strip()
        google_places_api_key = source.get("GOOGLE_PLACES_API_KEY", "").strip()
        google_places_radius_meters = _parse_positive_int(
            source.get("GOOGLE_PLACES_RADIUS_METERS", "2500"),
            "GOOGLE_PLACES_RADIUS_METERS",
        )
        google_places_max_results = _parse_positive_int(
            source.get("GOOGLE_PLACES_MAX_RESULTS", "10"),
            "GOOGLE_PLACES_MAX_RESULTS",
        )
        google_places_language_code = source.get(
            "GOOGLE_PLACES_LANGUAGE_CODE",
            "tr",
        ).strip()

        if provider not in {"json", "external", "google_places"}:
            raise ConfigurationError(
                "VENUE_PROVIDER must be 'json', 'external', or 'google_places'."
            )
        if provider == "google_places" and not google_places_api_key:
            raise ConfigurationError(
                "VENUE_PROVIDER=google_places requires GOOGLE_PLACES_API_KEY."
            )

        return cls(
            provider=provider,
            json_path=json_path,
            google_places_api_key=google_places_api_key,
            google_places_radius_meters=google_places_radius_meters,
            google_places_max_results=google_places_max_results,
            google_places_language_code=google_places_language_code,
        )


@dataclass(frozen=True)
class GoogleMapsSettings:
    """Browser-safe configuration for the Google Maps UI component."""

    browser_api_key: str = field(default="", repr=False)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "GoogleMapsSettings":
        """Load the referrer-restricted browser key when configured."""
        source = environment if environment is not None else os.environ
        return cls(
            browser_api_key=source.get(
                "GOOGLE_MAPS_BROWSER_API_KEY",
                "",
            ).strip()
        )


def _parse_boolean(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ConfigurationError(
        "LLM_ENABLED must be true or false."
    )


def _parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive integer.") from exc

    if parsed <= 0:
        raise ConfigurationError(f"{name} must be a positive integer.")
    return parsed
