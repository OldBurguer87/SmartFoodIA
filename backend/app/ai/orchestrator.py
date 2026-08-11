import json
import time
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

class OliviaOrchestrator:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider
        self.conversations = ConversationService()
        self.repository = ConversationRepository()

    def reply(self, db: Session, *, store_id: UUID, conversation_id: UUID,
              customer_message: str, customer_phone: str | None = None) -> str:
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
            ToolContext(db=db, store_id=store_id, customer_phone=customer_phone)
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
                    payload_json={"round": round_number, "tool_calls": len(response.tool_calls)},
                ),
            )

            if response.tool_calls:
                outputs = []
                for call in response.tool_calls:
                    tool_started = time.perf_counter()
                    try:
                        result = registry.execute(call.name, call.arguments)
                        payload = {
                            "ok": result.ok,
                            "data": result.data,
                            "error": result.error,
                            "requires_human": result.requires_human,
                        }
                        success = result.ok
                    except Exception as error:
                        payload = {"ok": False, "error": str(error), "requires_human": True}
                        success = False

                    self.conversations.record_event(
                        db,
                        store_id=store_id,
                        payload=AIEventCreate(
                            conversation_id=conversation_id,
                            event_type="TOOL_EXECUTION",
                            tool_name=call.name,
                            success=success,
                            duration_ms=int((time.perf_counter() - tool_started) * 1000),
                            payload_json={"arguments": call.arguments, "result": payload},
                            error_message=None if success else payload.get("error"),
                        ),
                    )
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(payload, ensure_ascii=False, default=str),
                    })
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

            raise OliviaExecutionError("O provedor não retornou texto nem chamada de ferramenta.")

        raise OliviaExecutionError("A Olívia excedeu o limite de chamadas de ferramentas.")

    @staticmethod
    def _provider_tools(registry: OliviaToolRegistry) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.input_schema,
                "strict": False,
            }
            for definition in registry.definitions()
        ]
