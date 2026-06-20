"""Create venue providers from application configuration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from app.config import ConfigurationError, VenueProviderSettings
from app.services.venue_providers import (
    ExternalVenueClient,
    ExternalVenueProvider,
    GooglePlacesClient,
    GooglePlacesVenueProvider,
    JsonVenueProvider,
    VenueProvider,
)


@dataclass(frozen=True)
class VenueProviderInspection:
    """Developer-facing venue provider runtime status."""

    provider: str
    json_path: str
    available: bool
    venue_count: int = 0
    sources: tuple[str, ...] = field(default_factory=tuple)
    error: str = ""


def load_venue_provider_settings(
    environment: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> VenueProviderSettings:
    """Return validated venue provider settings."""
    if environment is None:
        _load_dotenv(env_file)
    return VenueProviderSettings.from_environment(environment)


def create_venue_provider(
    settings: VenueProviderSettings,
    external_client: ExternalVenueClient | None = None,
) -> VenueProvider:
    """Create a trusted venue provider from settings."""
    if settings.provider == "json":
        if settings.json_path:
            return JsonVenueProvider(Path(settings.json_path))
        return JsonVenueProvider()

    if settings.provider == "external":
        if external_client is None:
            raise ConfigurationError(
                "VENUE_PROVIDER=external requires an external venue client."
            )
        return ExternalVenueProvider(external_client)

    if settings.provider == "google_places":
        return GooglePlacesVenueProvider(
            GooglePlacesClient(
                api_key=settings.google_places_api_key,
                language_code=settings.google_places_language_code,
            ),
            radius_meters=settings.google_places_radius_meters,
            max_result_count=settings.google_places_max_results,
        )

    raise ConfigurationError(
        f"Unsupported venue provider: {settings.provider}"
    )


def create_venue_provider_from_environment(
    environment: Mapping[str, str] | None = None,
    external_client: ExternalVenueClient | None = None,
    env_file: Path | None = None,
) -> VenueProvider:
    """Load settings and create the configured venue provider."""
    return create_venue_provider(
        load_venue_provider_settings(environment, env_file=env_file),
        external_client=external_client,
    )


def inspect_venue_provider(
    environment: Mapping[str, str] | None = None,
    external_client: ExternalVenueClient | None = None,
    env_file: Path | None = None,
) -> VenueProviderInspection:
    """Return runtime status for the configured venue provider."""
    try:
        settings = load_venue_provider_settings(environment, env_file=env_file)
    except Exception as exc:
        return VenueProviderInspection(
            provider=(
                environment.get("VENUE_PROVIDER", "unknown")
                if environment is not None
                else "unknown"
            ),
            json_path=(
                environment.get("VENUE_JSON_PATH", "")
                if environment is not None
                else ""
            ),
            available=False,
            error=str(exc),
        )

    if settings.provider == "google_places":
        return VenueProviderInspection(
            provider=settings.provider,
            json_path=settings.json_path,
            available=True,
            venue_count=0,
            sources=("google_places",),
        )

    try:
        provider = create_venue_provider(
            settings,
            external_client=external_client,
        )
        venues = provider.get_all()
    except Exception as exc:
        return VenueProviderInspection(
            provider=settings.provider,
            json_path=settings.json_path,
            available=False,
            error=str(exc),
        )

    sources = tuple(sorted({venue.source for venue in venues}))
    return VenueProviderInspection(
        provider=settings.provider,
        json_path=settings.json_path,
        available=True,
        venue_count=len(venues),
        sources=sources,
    )


def _load_dotenv(env_file: Path | None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise ConfigurationError(
            "python-dotenv is not installed. Install project requirements first."
        ) from exc

    load_dotenv(dotenv_path=env_file, override=False)
