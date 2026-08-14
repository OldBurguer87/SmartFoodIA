from __future__ import annotations

import json

from sqlalchemy import select

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.core.config import settings
from app.models.menu import StoreMenuDocument
from app.repositories.channel import ChannelRepository


class SendMenuPdfTool:
    definition = ToolDefinition(
        name="send_menu_pdf",
        description=(
            "Envia ao cliente, pelo WhatsApp, o PDF oficial do cardápio "
            "cadastrado para o estabelecimento. Use quando o cliente pedir "
            "explicitamente o cardápio em PDF ou escolher PDF após ser "
            "perguntado se prefere PDF ou ver o cardápio no WhatsApp."
        ),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    def execute(self) -> ToolResult:
        if not self.context.customer_phone:
            return ToolResult(
                ok=False,
                error="Telefone do cliente não disponível para envio do PDF.",
            )

        document = self.context.db.scalar(
            select(StoreMenuDocument).where(
                StoreMenuDocument.store_id == self.context.store_id
            )
        )

        if document is None:
            return ToolResult(
                ok=False,
                error="Não existe cardápio PDF cadastrado para este estabelecimento.",
            )

        account = ChannelRepository().get_account_by_store(
            self.context.db,
            store_id=self.context.store_id,
            provider="WHATSAPP_CLOUD",
        )

        if account is None:
            return ToolResult(
                ok=False,
                error="Canal WhatsApp não configurado para este estabelecimento.",
            )

        base_url = (settings.public_base_url or "").rstrip("/")
        if not base_url and settings.public_domain:
            base_url = f"https://{settings.public_domain.strip('/')}"

        if not base_url:
            return ToolResult(
                ok=False,
                error="URL pública do SmartFoodIA não configurada.",
            )

        document_url = (
            f"{base_url}/api/v1/public/menu/{document.public_token}"
        )

        payload = json.dumps(
            {
                "url": document_url,
                "filename": document.original_name,
                "caption": "Cardápio da Old Burguer 87 🍔",
            },
            ensure_ascii=False,
        )

        ChannelRepository().create_document_outbound(
            self.context.db,
            account=account,
            conversation_id=self.context.conversation_id,
            recipient=self.context.customer_phone,
            content=payload,
        )

        return ToolResult(
            ok=True,
            data={
                "queued": True,
                "filename": document.original_name,
            },
        )
