"""Provider-independent structured LLM client contract."""

from typing import Any, Protocol


class LLMServiceError(RuntimeError):
    """Raised when an LLM response is unavailable or invalid."""


class StructuredLLMClient(Protocol):
    """Generate validated JSON-like output for a named schema."""

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Return structured model output matching the requested schema."""
