from __future__ import annotations

from typing import Any
from uuid import UUID

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.schemas.conversation import HumanTicketCreate, KnowledgeGapCreate
from app.services.conversation import ConversationService
from app.services.human_relay import HumanRelayService


class RequestHumanHelpTool:
    definition = ToolDefinition(
        name="request_human_help",
        description=(
            "Cria alerta humano e lacuna de conhecimento quando uma informação "
            "não pode ser confirmada."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "minLength": 3},
                "customer_message": {"type": "string", "minLength": 1},
                "category": {
                    "type": "string",
                    "enum": [
                        "CATALOG",
                        "PRICE",
                        "AVAILABILITY",
                        "DELIVERY",
                        "PAYMENT",
                        "OTHER",
                    ],
                },
                "conversation_id": {
                    "type": ["string", "null"],
                    "format": "uuid",
                },
                "customer_id": {
                    "type": ["string", "null"],
                    "format": "uuid",
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "NORMAL", "HIGH", "URGENT"],
                },
                "create_knowledge_gap": {"type": "boolean"},
            },
            "required": ["reason", "customer_message", "category"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = ConversationService()

    def execute(
        self,
        *,
        reason: str,
        customer_message: str,
        category: str,
        conversation_id: str | None = None,
        customer_id: str | None = None,
        priority: str = "NORMAL",
        create_knowledge_gap: bool = True,
        **_: Any,
    ) -> ToolResult:
        conversation_uuid = (
            UUID(conversation_id)
            if conversation_id
            else self.context.conversation_id
        )
        customer_uuid = UUID(customer_id) if customer_id else None

        ticket = self.service.create_ticket(
            self.context.db,
            store_id=self.context.store_id,
            payload=HumanTicketCreate(
                conversation_id=conversation_uuid,
                customer_id=customer_uuid,
                category=category,
                priority=priority,
                reason=reason,
                customer_message=customer_message,
            ),
        )

        staff_notified = 0

        if conversation_uuid is not None:
            self.service.wait_for_human(
                self.context.db,
                conversation_id=conversation_uuid,
                reason=reason,
                ticket_id=ticket.id,
            )
            staff_notified = HumanRelayService().notify_waiting(
                self.context.db,
                store_id=self.context.store_id,
                conversation_id=conversation_uuid,
                reason=reason,
            )

        gap_id = None
        if create_knowledge_gap:
            gap = self.service.create_or_increment_gap(
                self.context.db,
                store_id=self.context.store_id,
                payload=KnowledgeGapCreate(
                    conversation_id=conversation_uuid,
                    ticket_id=ticket.id,
                    question=customer_message,
                ),
            )
            gap_id = str(gap.id)

        return ToolResult(
            ok=True,
            requires_human=True,
            data={
                "ticket_id": str(ticket.id),
                "knowledge_gap_id": gap_id,
                "store_id": str(self.context.store_id),
                "customer_phone": self.context.customer_phone,
                "reason": reason,
                "customer_message": customer_message,
                "category": category,
                "priority": priority,
                "status": ticket.status,
                "staff_notified": staff_notified,
            },
        )
