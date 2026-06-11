"""OpenAI Responses API adapter for the structured LLM contract."""

import json
from typing import Any

from app.llm.client import LLMServiceError


class OpenAIStructuredClient:
    """Generate JSON Schema-constrained output through the Responses API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        sdk_client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise LLMServiceError("OpenAI API key cannot be empty.")
        if not model.strip():
            raise LLMServiceError("OpenAI model name cannot be empty.")

        self.model = model.strip()
        self._client = sdk_client or _create_openai_sdk_client(api_key.strip())

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Call OpenAI and return a decoded object matching the requested schema."""
        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=user_prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": json_schema,
                    }
                },
            )
        except Exception as exc:
            raise LLMServiceError(
                f"OpenAI request failed: {exc}"
            ) from exc

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise LLMServiceError(
                "OpenAI returned no structured text output."
            )

        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise LLMServiceError(
                "OpenAI returned structured output that was not valid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise LLMServiceError(
                "OpenAI structured output must be a JSON object."
            )

        return payload


def _create_openai_sdk_client(api_key: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMServiceError(
            "The OpenAI SDK is not installed. Install project requirements first."
        ) from exc

    return OpenAI(api_key=api_key)
