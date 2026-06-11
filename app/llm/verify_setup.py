"""Minimal real API check for the configured structured LLM provider."""

from typing import Any

from app.config import ConfigurationError
from app.llm.client import LLMServiceError, StructuredLLMClient
from app.llm.factory import create_llm_client_from_environment


CONNECTION_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ok"],
        },
        "message": {"type": "string"},
    },
    "required": ["status", "message"],
    "additionalProperties": False,
}


def run_connection_check(client: StructuredLLMClient) -> dict[str, Any]:
    """Make a minimal structured request to verify provider configuration."""
    return client.generate_structured(
        system_prompt=(
            "Return the requested connection-check object. "
            "Do not include extra fields."
        ),
        user_prompt="Confirm that structured output is working.",
        schema_name="connection_check",
        json_schema=CONNECTION_CHECK_SCHEMA,
    )


def main() -> None:
    """Load .env, call the provider once, and print the verified payload."""
    try:
        client = create_llm_client_from_environment()
        payload = run_connection_check(client)
    except (ConfigurationError, LLMServiceError) as exc:
        raise SystemExit(f"LLM setup check failed: {exc}") from exc

    print(f"LLM connection status: {payload['status']}")
    print(f"Provider message: {payload['message']}")


if __name__ == "__main__":
    main()
