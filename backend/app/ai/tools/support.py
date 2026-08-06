from __future__ import annotations

from typing import Any

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult


class RequestHumanHelpTool:
    definition = ToolDefinition(
        name="request_human_help",
        description=(
            "Registra a necessidade de ajuda humana quando uma informação "
            "não pode ser confirmada. Nesta versão apenas devolve o payload "
            "estruturado; a persistência do ticket virá na próxima etapa."
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
            },
            "required": ["reason", "customer_message", "category"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    def execute(
        self,
        *,
        reason: str,
        customer_message: str,
        category: str,
        **_: Any,
    ) -> ToolResult:
        return ToolResult(
            ok=True,
            requires_human=True,
            data={
                "store_id": str(self.context.store_id),
                "customer_phone": self.context.customer_phone,
                "reason": reason,
                "customer_message": customer_message,
                "category": category,
                "status": "PENDING_HUMAN",
            },
        )
