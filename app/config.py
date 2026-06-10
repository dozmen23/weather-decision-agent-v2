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


def _parse_boolean(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ConfigurationError(
        "LLM_ENABLED must be true or false."
    )
