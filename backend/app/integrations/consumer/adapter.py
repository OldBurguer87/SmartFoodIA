from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.contracts.orders import IntegrationEvent
from app.integrations.consumer.mapper import map_order
from app.integrations.consumer.status import INTERNAL_EVENT, STATUS_TO_INTERNAL
from app.models.order import OrderEvent
from app.models.payment import PaymentReceipt
from app.repositories.order import OrderRepository


class IntegrationOrderNotFound(LookupError):
    pass


class IntegrationStatusError(ValueError):
    pass


_STATUS_RANK = {
    "READY_FOR_INTEGRATION": 0,
    "CONFIRMED": 1,
    "READY": 2,
    "DISPATCHED": 3,
    "CONCLUDED": 4,
}

_TERMINAL_STATUSES = {"CONCLUDED", "CANCELLED"}


class ConsumerPartnerAdapter:
    provider = "CONSUMER"

    def __init__(self, order_repository: OrderRepository | None = None):
        self.orders = order_repository or OrderRepository()

    @staticmethod
    def _ensure_released(order) -> None:
        release_at = order.release_at

        if release_at is None:
            return

        if release_at.tzinfo is None:
            release_at = release_at.replace(tzinfo=timezone.utc)

        if release_at > datetime.now(timezone.utc):
            raise IntegrationOrderNotFound(
                "Pedido agendado ainda não liberado para integração."
            )

    @staticmethod
    def _requires_pix_confirmation(order) -> bool:
        return (
            str(order.payment_method or "").upper() == "PIX"
            and str(order.service_mode or "").upper()
            in {"DELIVERY", "TAKEOUT"}
        )

    @classmethod
    def _ensure_payment_released(
        cls,
        db: Session,
        order,
    ) -> None:
        if not cls._requires_pix_confirmation(order):
            return

        confirmed_receipt_id = db.scalar(
            select(PaymentReceipt.id)
            .where(
                PaymentReceipt.store_id == order.store_id,
                PaymentReceipt.order_id == order.id,
                PaymentReceipt.status.in_(
                    ["AUTO_CONFIRMED", "HUMAN_CONFIRMED"]
                ),
            )
            .limit(1)
        )

        if confirmed_receipt_id is None:
            raise IntegrationOrderNotFound(
                "Pedido PIX ainda não confirmado para integração."
            )

    def poll(self, db: Session, *, store_id: UUID, limit: int = 100):
        return [
            IntegrationEvent(
                event.id,
                event.order_id,
                event.created_at.astimezone(timezone.utc),
                event.code,
                event.full_code,
            )
            for event in self.orders.list_pending_events(
                db,
                store_id=store_id,
                limit=limit,
            )
        ]

    def serialize_order(
        self,
        db: Session,
        *,
        store_id: UUID,
        order_id: UUID,
        integration,
    ):
        order = self.orders.get_for_store(
            db,
            store_id=store_id,
            order_id=order_id,
        )
        if not order:
            raise IntegrationOrderNotFound("Pedido não encontrado.")

        self._ensure_released(order)
        self._ensure_payment_released(db, order)
        return map_order(order, integration)

    def acknowledge_details_request(
        self,
        db: Session,
        *,
        store_id: UUID,
        order_id: UUID,
        code: str,
        full_code: str,
        reason: str | None = None,
    ):
        order = self.orders.get_for_store(
            db,
            store_id=store_id,
            order_id=order_id,
        )
        if not order:
            raise IntegrationOrderNotFound("Pedido não encontrado.")

        self._ensure_released(order)

        normalized = code.strip().upper()
        normalized_full = (full_code or "ORDER_DETAILS_REQUESTED").strip().upper()

        if normalized != "ODR" or normalized_full != "ORDER_DETAILS_REQUESTED":
            raise IntegrationStatusError(
                "Evento suportado neste endpoint: ODR / ORDER_DETAILS_REQUESTED."
            )

        self._ensure_payment_released(db, order)

        existing = next(
            (
                event
                for event in order.events
                if event.code == normalized
                and event.full_code == normalized_full
            ),
            None,
        )
        if existing:
            return IntegrationEvent(
                existing.id,
                existing.order_id,
                existing.created_at.astimezone(timezone.utc),
                existing.code,
                existing.full_code,
            )

        for event in order.events:
            if event.code == "PLC" and event.status == "PENDING":
                event.status = "DELIVERED"

        event = OrderEvent(
            id=uuid4(),
            order_id=order.id,
            code=normalized,
            full_code=normalized_full,
            status="DELIVERED",
            reason=reason,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        return IntegrationEvent(
            event.id,
            event.order_id,
            event.created_at.astimezone(timezone.utc),
            event.code,
            event.full_code,
        )

    def apply_external_status(
        self,
        db: Session,
        *,
        store_id: UUID,
        order_id: UUID,
        status: str,
        justification: str | None = None,
    ):
        order = self.orders.get_for_store(
            db,
            store_id=store_id,
            order_id=order_id,
        )
        if not order:
            raise IntegrationOrderNotFound("Pedido não encontrado.")

        self._ensure_released(order)
        self._ensure_payment_released(db, order)

        normalized = status.strip().upper().replace("-", "_").replace(" ", "_")
        compact = normalized.replace("_", "")
        normalized = next(
            (
                key
                for key in STATUS_TO_INTERNAL
                if key.replace("_", "") == compact
            ),
            normalized,
        )

        internal = STATUS_TO_INTERNAL.get(normalized)
        if not internal:
            raise IntegrationStatusError(f"Status não suportado: {status}.")

        if order.status == internal:
            return internal, False

        current = order.status

        # Estados terminais não podem ser reabertos por callbacks tardios.
        if current in _TERMINAL_STATUSES:
            return current, False

        # Evita regressões como DISPATCHED -> READY ou READY -> CONFIRMED.
        current_rank = _STATUS_RANK.get(current)
        incoming_rank = _STATUS_RANK.get(internal)
        if (
            current_rank is not None
            and incoming_rank is not None
            and incoming_rank < current_rank
        ):
            return current, False

        order.status = internal
        code, full_code = INTERNAL_EVENT[internal]
        db.add(
            OrderEvent(
                order_id=order.id,
                code=code,
                full_code=full_code,
                status="DELIVERED",
                reason=justification,
            )
        )
        db.commit()
        return internal, True
