from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.repositories.channel import ChannelRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.order import OrderRepository
from app.schemas.conversation import MessageCreate
from app.services.conversation import ConversationService


STATUS_MESSAGES = {
    "CONFIRMED": "Seu pedido foi confirmado pela {store_name}.",
    "READY": "Seu pedido está pronto para retirada.",
    "DISPATCHED": "Seu pedido saiu para entrega.",
    "CONCLUDED": "Seu pedido foi finalizado. Obrigado pela preferência!",
    "CANCELLED": (
        "Seu pedido foi cancelado. Entre em contato caso precise de ajuda."
    ),
}


class WhatsAppOrderStatusNotifier:
    def __init__(
        self,
        *,
        orders: OrderRepository | None = None,
        channels: ChannelRepository | None = None,
        conversations: ConversationRepository | None = None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self.orders = orders or OrderRepository()
        self.channels = channels or ChannelRepository()
        self.conversations = conversations or ConversationRepository()
        self.conversation_service = (
            conversation_service
            or ConversationService(self.conversations)
        )

    def notify_status_change(
        self,
        db: Session,
        *,
        store_id: UUID,
        order_id: UUID,
        status: str,
    ) -> bool:
        template = STATUS_MESSAGES.get(status)
        if template is None:
            return False

        order = self.orders.get_for_store(
            db,
            store_id=store_id,
            order_id=order_id,
        )
        if order is None or not order.customer_phone:
            return False

        store = db.get(Store, store_id)
        if store is None:
            return False

        account = self.channels.get_account_by_store(
            db,
            store_id=store_id,
            provider="WHATSAPP_CLOUD",
        )
        if account is None:
            return False

        if status == "READY" and order.service_mode == "DELIVERY":
            template = "Seu pedido está pronto e aguardando sair para entrega."

        message = template.format(store_name=store.name)
        content = f"Pedido #{order.display_id}: {message}"

        conversation = self.conversations.get_open(
            db,
            store_id=store_id,
            channel="WHATSAPP",
            external_conversation_id=order.customer_phone,
        )

        conversation_id = (
            conversation.id
            if conversation is not None
            else None
        )

        self.channels.create_outbound(
            db,
            account=account,
            conversation_id=conversation_id,
            recipient=order.customer_phone,
            content=content,
        )

        if conversation is not None:
            self.conversation_service.add_message(
                db,
                conversation_id=conversation.id,
                payload=MessageCreate(
                    direction="OUTBOUND",
                    sender_type="SYSTEM",
                    content_type="TEXT",
                    content=content,
                    metadata_json={
                        "source": "ORDER_STATUS_NOTIFICATION",
                        "order_id": str(order.id),
                        "order_display_id": order.display_id,
                        "status": status,
                    },
                ),
            )

        return True
