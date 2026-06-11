"""Create provider adapters from environment-based application settings."""

from pathlib import Path
from typing import Mapping

from app.config import ConfigurationError, LLMSettings
from app.llm.client import StructuredLLMClient
from app.llm.openai_client import OpenAIStructuredClient


def load_llm_settings(
    env_file: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> LLMSettings:
    """Load an optional .env file and return validated LLM settings."""
    if environment is None:
        _load_dotenv(env_file)
    return LLMSettings.from_environment(environment)


def create_llm_client(settings: LLMSettings) -> StructuredLLMClient:
    """Create the configured provider adapter."""
    if not settings.enabled:
        raise ConfigurationError(
            "LLM integration is disabled. Set LLM_ENABLED=true to enable it."
        )

    if settings.provider.casefold() == "openai":
        return OpenAIStructuredClient(
            api_key=settings.api_key,
            model=settings.model,
        )

    raise ConfigurationError(
        f"Unsupported LLM provider: {settings.provider}"
    )


def create_llm_client_from_environment(
    env_file: Path | None = None,
) -> StructuredLLMClient:
    """Load settings and create the configured LLM provider adapter."""
    return create_llm_client(load_llm_settings(env_file=env_file))


def _load_dotenv(env_file: Path | None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise ConfigurationError(
            "python-dotenv is not installed. Install project requirements first."
        ) from exc

    load_dotenv(dotenv_path=env_file, override=False)
