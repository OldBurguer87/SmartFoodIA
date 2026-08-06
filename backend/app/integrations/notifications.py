from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.repositories.channel import ChannelRepository
from app.repositories.order import OrderRepository


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
    ) -> None:
        self.orders = orders or OrderRepository()
        self.channels = channels or ChannelRepository()

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

        message = template.format(store_name=store.name)
        self.channels.create_outbound(
            db,
            account=account,
            conversation_id=None,
            recipient=order.customer_phone,
            content=f"Pedido #{order.display_id}: {message}",
        )
        return True
