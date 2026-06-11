"""Tests for the OpenAI structured-output adapter and factory."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import ConfigurationError, LLMSettings
from app.llm.client import LLMServiceError
from app.llm.factory import create_llm_client, load_llm_settings
from app.llm.openai_client import OpenAIStructuredClient
from app.llm.verify_setup import run_connection_check


class FakeResponsesAPI:
    def __init__(
        self,
        output_text: str = '{"result": "ok"}',
        error: Exception | None = None,
    ) -> None:
        self.output_text = output_text
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_text=self.output_text)


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponsesAPI) -> None:
        self.responses = responses


class FakeStructuredClient:
    def __init__(self) -> None:
        self.call: dict[str, object] | None = None

    def generate_structured(self, **kwargs):
        self.call = kwargs
        return {"status": "ok", "message": "Structured output is ready."}


class OpenAIStructuredClientTests(unittest.TestCase):
    def test_adapter_sends_strict_json_schema_to_responses_api(self) -> None:
        responses = FakeResponsesAPI(
            json.dumps({"summary": "Grounded explanation."})
        )
        client = OpenAIStructuredClient(
            api_key="test-key",
            model="test-model",
            sdk_client=FakeOpenAIClient(responses),
        )
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }

        payload = client.generate_structured(
            system_prompt="System rules",
            user_prompt="User facts",
            schema_name="test_schema",
            json_schema=schema,
        )

        self.assertEqual(payload, {"summary": "Grounded explanation."})
        request = responses.calls[0]
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["instructions"], "System rules")
        self.assertEqual(request["input"], "User facts")
        self.assertEqual(
            request["text"]["format"],
            {
                "type": "json_schema",
                "name": "test_schema",
                "strict": True,
                "schema": schema,
            },
        )

    def test_adapter_wraps_provider_errors(self) -> None:
        client = OpenAIStructuredClient(
            api_key="test-key",
            model="test-model",
            sdk_client=FakeOpenAIClient(
                FakeResponsesAPI(error=RuntimeError("provider unavailable"))
            ),
        )

        with self.assertRaisesRegex(LLMServiceError, "OpenAI request failed"):
            client.generate_structured(
                system_prompt="system",
                user_prompt="user",
                schema_name="schema",
                json_schema={"type": "object"},
            )

    def test_adapter_rejects_invalid_json_output(self) -> None:
        client = OpenAIStructuredClient(
            api_key="test-key",
            model="test-model",
            sdk_client=FakeOpenAIClient(FakeResponsesAPI("not-json")),
        )

        with self.assertRaisesRegex(LLMServiceError, "not valid JSON"):
            client.generate_structured(
                system_prompt="system",
                user_prompt="user",
                schema_name="schema",
                json_schema={"type": "object"},
            )

    def test_adapter_rejects_empty_credentials(self) -> None:
        with self.assertRaisesRegex(LLMServiceError, "API key cannot be empty"):
            OpenAIStructuredClient(api_key="", model="test-model")

    @patch("app.llm.factory.OpenAIStructuredClient")
    def test_factory_creates_openai_adapter(self, adapter_class) -> None:
        settings = LLMSettings(
            enabled=True,
            provider="openai",
            model="configured-model",
            api_key="configured-key",
        )

        client = create_llm_client(settings)

        self.assertIs(client, adapter_class.return_value)
        adapter_class.assert_called_once_with(
            api_key="configured-key",
            model="configured-model",
        )

    def test_factory_rejects_disabled_llm(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "disabled"):
            create_llm_client(LLMSettings())

    def test_dotenv_file_is_loaded_without_overriding_existing_environment(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "LLM_ENABLED=true",
                        "LLM_PROVIDER=openai",
                        "LLM_MODEL=file-model",
                        "LLM_API_KEY=file-key",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"LLM_MODEL": "environment-model"},
                clear=True,
            ):
                settings = load_llm_settings(env_file=env_path)

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.model, "environment-model")
        self.assertEqual(settings.api_key, "file-key")

    def test_connection_check_uses_structured_client_contract(self) -> None:
        client = FakeStructuredClient()

        payload = run_connection_check(client)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(client.call["schema_name"], "connection_check")


if __name__ == "__main__":
    unittest.main()
