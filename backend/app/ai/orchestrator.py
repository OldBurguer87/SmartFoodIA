import json
import time
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.olivia_prompt import OLIVIA_INSTRUCTIONS
from app.ai.providers.base import AIProvider
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import OliviaToolRegistry
from app.core.config import settings
from app.repositories.conversation import ConversationRepository
from app.schemas.conversation import AIEventCreate, MessageCreate
from app.services.conversation import ConversationService


class OliviaExecutionError(RuntimeError):
    pass


def _nullable_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Allow null in an OpenAI-facing JSON Schema without changing Core semantics."""
    result = deepcopy(schema)
    schema_type = result.get("type")

    if isinstance(schema_type, str):
        if schema_type != "null":
            result["type"] = [schema_type, "null"]
    elif isinstance(schema_type, list):
        if "null" not in schema_type:
            result["type"] = [*schema_type, "null"]
    elif "anyOf" in result:
        result["anyOf"] = [*result["anyOf"], {"type": "null"}]
    elif "oneOf" in result:
        result["oneOf"] = [*result["oneOf"], {"type": "null"}]
    else:
        return {"anyOf": [result, {"type": "null"}]}

    if "enum" in result and None not in result["enum"]:
        result["enum"] = [*result["enum"], None]

    return result


def _responses_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize tool schemas to the shape required by the Responses API.

    The Responses API validates object schemas with every property listed in
    ``required``. Internally optional fields remain optional by allowing null;
    null values are removed before invoking the Core tool so Python defaults
    continue to apply exactly as before.
    """
    result = deepcopy(schema)

    properties = result.get("properties")
    schema_type = result.get("type")
    is_object = schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )

    if is_object and isinstance(properties, dict):
        originally_required = set(result.get("required") or [])
        normalized_properties: dict[str, Any] = {}

        for name, property_schema in properties.items():
            normalized = _responses_tool_schema(property_schema)
            if name not in originally_required:
                normalized = _nullable_schema(normalized)
            normalized_properties[name] = normalized

        result["properties"] = normalized_properties
        result["required"] = list(properties.keys())
        result["additionalProperties"] = False

    if isinstance(result.get("items"), dict):
        result["items"] = _responses_tool_schema(result["items"])

    for keyword in ("anyOf", "oneOf", "allOf"):
        if isinstance(result.get(keyword), list):
            result[keyword] = [
                _responses_tool_schema(item) if isinstance(item, dict) else item
                for item in result[keyword]
            ]

    return result


def _drop_null_arguments(value: Any) -> Any:
    """Remove nullable placeholders before calling the internal tool."""
    if isinstance(value, dict):
        return {
            key: _drop_null_arguments(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_drop_null_arguments(item) for item in value]
    return value


class OliviaOrchestrator:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider
        self.conversations = ConversationService()
        self.repository = ConversationRepository()

    def reply(
        self,
        db: Session,
        *,
        store_id: UUID,
        conversation_id: UUID,
        customer_message: str,
        customer_phone: str | None = None,
    ) -> str:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None or conversation.store_id != store_id:
            raise OliviaExecutionError("Conversa não encontrada para esta loja.")

        self.conversations.add_message(
            db,
            conversation_id=conversation_id,
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content=customer_message,
            ),
        )

        history = self.repository.list_messages(db, conversation_id, limit=30)
        input_items = [
            {
                "role": "user" if message.sender_type == "CUSTOMER" else "assistant",
                "content": message.content,
            }
            for message in history
        ]
        registry = OliviaToolRegistry(
            ToolContext(
                db=db,
                store_id=store_id,
                customer_phone=customer_phone,
            )
        )
        previous_response_id = None

        for round_number in range(1, settings.olivia_max_tool_rounds + 1):
            started = time.perf_counter()
            response = self.provider.respond(
                instructions=OLIVIA_INSTRUCTIONS,
                input_items=input_items,
                tools=self._provider_tools(registry),
                previous_response_id=previous_response_id,
            )
            previous_response_id = response.response_id
            self.conversations.record_event(
                db,
                store_id=store_id,
                payload=AIEventCreate(
                    conversation_id=conversation_id,
                    event_type="AI_RESPONSE",
                    success=True,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    payload_json={
                        "round": round_number,
                        "tool_calls": len(response.tool_calls),
                    },
                ),
            )

            if response.tool_calls:
                outputs = []
                for call in response.tool_calls:
                    tool_started = time.perf_counter()
                    try:
                        arguments = _drop_null_arguments(call.arguments)
                        result = registry.execute(call.name, arguments)
                        payload = {
                            "ok": result.ok,
                            "data": result.data,
                            "error": result.error,
                            "requires_human": result.requires_human,
                        }
                        success = result.ok
                    except Exception as error:
                        payload = {
                            "ok": False,
                            "error": str(error),
                            "requires_human": True,
                        }
                        success = False

                    self.conversations.record_event(
                        db,
                        store_id=store_id,
                        payload=AIEventCreate(
                            conversation_id=conversation_id,
                            event_type="TOOL_EXECUTION",
                            tool_name=call.name,
                            success=success,
                            duration_ms=int(
                                (time.perf_counter() - tool_started) * 1000
                            ),
                            payload_json={
                                "arguments": call.arguments,
                                "result": payload,
                            },
                            error_message=None if success else payload.get("error"),
                        ),
                    )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(
                                payload,
                                ensure_ascii=False,
                                default=str,
                            ),
                        }
                    )
                input_items = outputs
                continue

            if response.text:
                self.conversations.add_message(
                    db,
                    conversation_id=conversation_id,
                    payload=MessageCreate(
                        direction="OUTBOUND",
                        sender_type="OLIVIA",
                        content=response.text,
                    ),
                )
                return response.text

            raise OliviaExecutionError(
                "O provedor não retornou texto nem chamada de ferramenta."
            )

        raise OliviaExecutionError(
            "A Olívia excedeu o limite de chamadas de ferramentas."
        )

    @staticmethod
    def _provider_tools(registry: OliviaToolRegistry) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": definition.name,
                "description": definition.description,
                "parameters": _responses_tool_schema(definition.input_schema),
                "strict": False,
            }
            for definition in registry.definitions()
        ]
