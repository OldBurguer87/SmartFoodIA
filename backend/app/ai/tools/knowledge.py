from __future__ import annotations

from typing import Any

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.services.conversation import ConversationService


class SearchKnowledgeTool:
    definition = ToolDefinition(
        name="search_knowledge",
        description=(
            "Consulta respostas já aprovadas pela equipe da loja. "
            "Use antes de solicitar ajuda humana para dúvidas institucionais."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 3},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = ConversationService()

    def execute(self, *, question: str, **_: Any) -> ToolResult:
        gap = self.service.find_knowledge_answer(
            self.context.db,
            store_id=self.context.store_id,
            question=question,
        )
        if gap is None:
            return ToolResult(
                ok=False,
                error="Resposta aprovada não encontrada na base de conhecimento.",
                requires_human=False,
            )
        return ToolResult(
            ok=True,
            data={
                "question": gap.question,
                "answer": gap.answer,
                "knowledge_gap_id": str(gap.id),
            },
        )
