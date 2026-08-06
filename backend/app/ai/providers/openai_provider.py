import json
from typing import Any
from app.ai.providers.base import ProviderResponse, ProviderToolCall
from app.core.config import settings

class OpenAIProviderConfigurationError(RuntimeError):
    pass

class OpenAIResponsesProvider:
    def __init__(self, *, client=None, model: str | None = None) -> None:
        if client is None and not settings.openai_api_key:
            raise OpenAIProviderConfigurationError("OPENAI_API_KEY não foi configurada.")
        if client is None:
            from openai import OpenAI
            client = OpenAI(
            api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )
        self.client = client
        self.model = model or settings.openai_model

    def respond(self, *, instructions: str, input_items: list[dict[str, Any]],
                tools: list[dict[str, Any]],
                previous_response_id: str | None = None) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
        }
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id
        response = self.client.responses.create(**kwargs)
        calls = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "function_call":
                raw = getattr(item, "arguments", "{}") or "{}"
                calls.append(ProviderToolCall(
                    call_id=getattr(item, "call_id"),
                    name=getattr(item, "name"),
                    arguments=raw if isinstance(raw, dict) else json.loads(raw),
                ))
        output_text = getattr(response, "output_text", None)
        return ProviderResponse(
            response_id=getattr(response, "id", None),
            text=output_text.strip() if isinstance(output_text, str) and output_text.strip() else None,
            tool_calls=calls,
        )
