from __future__ import annotations

import hashlib
import hmac
from datetime import timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.integration import StoreIntegration
from app.models.order import Order, OrderEvent
from app.repositories.integration import IntegrationRepository
from app.repositories.order import OrderRepository
from app.schemas.consumer import (
    ConsumerEventRead,
    ConsumerOrderEventRequest,
    ConsumerPollingResponse,
    ConsumerStatusRequest,
    ConsumerStatusResponse,
)


class ConsumerAuthenticationError(PermissionError):
    pass


class ConsumerNotFoundError(LookupError):
    pass


class ConsumerValidationError(ValueError):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ConsumerPartnerService:
    STATUS_MAP = {
        "CONFIRMED": "CONFIRMED",
        "CANCELLED": "CANCELLED",
        "READY_TO_PICKUP": "READY",
        "READY": "READY",
        "DISPATCHED": "DISPATCHED",
        "OUT_FOR_DELIVERY": "DISPATCHED",
        "CONCLUDED": "CONCLUDED",
        "DELIVERED": "CONCLUDED",
    }

    EVENT_CODES = {
        "CONFIRMED": ("CFM", "CONFIRMED"),
        "CANCELLED": ("CAN", "CANCELLED"),
        "READY": ("RTP", "READY_TO_PICKUP"),
        "DISPATCHED": ("DSP", "DISPATCHED"),
        "CONCLUDED": ("CON", "CONCLUDED"),
    }

    def __init__(
        self,
        integration_repository: IntegrationRepository | None = None,
        order_repository: OrderRepository | None = None,
    ) -> None:
        self.integration_repository = (
            integration_repository or IntegrationRepository()
        )
        self.order_repository = order_repository or OrderRepository()

    def authenticate(
        self,
        db: Session,
        *,
        store_slug: str,
        authorization: str | None,
    ) -> tuple[Store, StoreIntegration]:
        store = self.integration_repository.get_store_by_slug(db, store_slug)
        if store is None:
            raise ConsumerAuthenticationError("Loja ou integração inválida.")

        integration = self.integration_repository.get_store_integration(
            db,
            store_id=store.id,
            provider="CONSUMER",
        )
        if integration is None:
            raise ConsumerAuthenticationError("Loja ou integração inválida.")

        if not authorization or not authorization.startswith("Bearer "):
            raise ConsumerAuthenticationError("Token ausente ou inválido.")

        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise ConsumerAuthenticationError("Token ausente ou inválido.")

        if not hmac.compare_digest(hash_token(token), integration.token_hash):
            raise ConsumerAuthenticationError("Token ausente ou inválido.")

        return store, integration

    def polling(
        self,
        db: Session,
        *,
        store: Store,
        limit: int = 100,
    ) -> ConsumerPollingResponse:
        events = self.order_repository.list_pending_events(
            db,
            store_id=store.id,
            limit=limit,
        )
        return ConsumerPollingResponse(
            items=[
                ConsumerEventRead(
                    id=event.id,
                    orderId=event.order_id,
                    createdAt=event.created_at.astimezone(timezone.utc),
                    fullCode=event.full_code,
                    code=event.code,
                )
                for event in events
            ]
        )

    def order_details(
        self,
        db: Session,
        *,
        store: Store,
        integration: StoreIntegration,
        order_id: UUID,
    ) -> dict:
        order = self.order_repository.get_for_store(
            db,
            store_id=store.id,
            order_id=order_id,
        )
        if order is None:
            raise ConsumerNotFoundError("Pedido não encontrado.")

        delivery = None
        takeout = None
        if order.service_mode == "DELIVERY":
            delivery = {
                "mode": "DEFAULT",
                "pickupCode": order.display_id,
                "deliveredBy": "MERCHANT",
                "deliveryDateTime": order.created_at.astimezone(
                    timezone.utc
                ).isoformat(),
                "deliveryAddress": {
                    "country": "BR",
                    "state": order.address_state,
                    "city": order.address_city,
                    "postalCode": order.address_postal_code or "",
                    "streetName": order.address_street,
                    "streetNumber": order.address_number,
                    "neighborhood": order.address_neighborhood,
                    "complement": order.address_complement,
                    "reference": order.address_reference,
                },
            }
        else:
            takeout = {
                "mode": "DEFAULT",
                "takeoutDateTime": order.created_at.astimezone(
                    timezone.utc
                ).isoformat(),
            }

        prepaid = (
            order.total if order.payment_type == "PREPAID" else Decimal("0.00")
        )
        pending = (
            Decimal("0.00")
            if order.payment_type == "PREPAID"
            else order.total
        )

        item_payloads = []
        for index, item in enumerate(order.items, start=1):
            item_payloads.append(
                {
                    "id": str(item.id),
                    "uniqueId": str(item.id),
                    "index": index,
                    "externalCode": item.product_external_code,
                    "name": item.product_name,
                    "quantity": item.quantity,
                    "unit": "UN",
                    "unitPrice": float(item.unit_price),
                    "price": float(item.total_price),
                    "totalPrice": float(item.total_price),
                    "observations": item.observations,
                    "optionsPrice": float(
                        sum(
                            modifier.total_price
                            for modifier in item.modifiers
                        )
                    ),
                    "addition": 0,
                    "options": [
                        {
                            "id": str(modifier.id),
                            "index": modifier_index,
                            "externalCode": modifier.modifier_external_code,
                            "name": modifier.modifier_name,
                            "quantity": modifier.quantity,
                            "unit": "UN",
                            "unitPrice": float(modifier.unit_price),
                            "price": float(modifier.total_price),
                            "addition": 0,
                        }
                        for modifier_index, modifier in enumerate(
                            item.modifiers,
                            start=1,
                        )
                    ],
                }
            )

        return {
            "item": {
                "id": str(order.id),
                "displayId": order.display_id,
                "orderType": order.service_mode,
                "salesChannel": "PARTNER",
                "orderTiming": "IMMEDIATE",
                "createdAt": order.created_at.astimezone(timezone.utc).isoformat(),
                "preparationStartDateTime": order.created_at.astimezone(
                    timezone.utc
                ).isoformat(),
                "merchant": {
                    "id": integration.merchant_external_id,
                    "name": integration.merchant_name,
                },
                "items": item_payloads,
                "total": {
                    "subTotal": float(order.subtotal),
                    "deliveryFee": float(order.delivery_fee),
                    "orderAmount": float(order.total),
                    "benefits": float(order.discount),
                    "additionalFees": 0,
                },
                "payments": {
                    "methods": [
                        {
                            "method": order.payment_method,
                            "type": order.payment_type,
                            "currency": "BRL",
                            "value": float(order.total),
                            "prepaid": order.payment_type == "PREPAID",
                            "cash": (
                                {"changeFor": float(order.change_for)}
                                if order.payment_method == "CASH"
                                and order.change_for is not None
                                else None
                            ),
                            "card": None,
                            "wallet": None,
                        }
                    ],
                    "pending": float(pending),
                    "prepaid": float(prepaid),
                },
                "customer": {
                    "id": str(order.customer_id),
                    "name": order.customer_name,
                    "phone": {
                        "number": order.customer_phone,
                        "localizer": order.display_id,
                        "localizerExpiration": order.created_at.astimezone(
                            timezone.utc
                        ).isoformat(),
                    },
                    "documentNumber": None,
                },
                "delivery": delivery,
                "takeout": takeout,
                "indoor": None,
                "schedule": None,
                "extraInfo": None,
            },
            "statusCode": 0,
            "reasonPhrase": None,
        }

    def receive_order_event(
        self,
        db: Session,
        *,
        store: Store,
        payload: ConsumerOrderEventRequest,
    ) -> ConsumerEventRead:
        order = self.order_repository.get_for_store(
            db,
            store_id=store.id,
            order_id=payload.OrderId,
        )
        if order is None:
            raise ConsumerNotFoundError("Pedido não encontrado.")

        if payload.EventCode.upper() == "ODR":
            for event in order.events:
                if event.code == "PLC" and event.status == "PENDING":
                    event.status = "DELIVERED"

        full_code = payload.EventFullCode or "ORDER_DETAILS_REQUESTED"
        event = OrderEvent(
            id=uuid4(),
            order_id=order.id,
            code=payload.EventCode.upper(),
            full_code=full_code,
            status="DELIVERED",
            reason=payload.EventFull,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        return ConsumerEventRead(
            id=event.id,
            orderId=event.order_id,
            createdAt=event.created_at.astimezone(timezone.utc),
            fullCode=event.full_code,
            code=event.code,
        )

    def update_status(
        self,
        db: Session,
        *,
        store: Store,
        payload: ConsumerStatusRequest,
    ) -> ConsumerStatusResponse:
        order = self.order_repository.get_for_store(
            db,
            store_id=store.id,
            order_id=payload.orderId,
        )
        if order is None:
            raise ConsumerNotFoundError("Pedido não encontrado.")

        normalized = payload.status.strip().upper()
        internal_status = self.STATUS_MAP.get(normalized)
        if internal_status is None:
            raise ConsumerValidationError(
                f"Status não suportado: {payload.status}."
            )

        if order.status == internal_status:
            return ConsumerStatusResponse(
                reasonPhrase=(
                    f"{order.id} já estava com status '{internal_status}'."
                )
            )

        order.status = internal_status
        code, full_code = self.EVENT_CODES[internal_status]
        db.add(
            OrderEvent(
                order_id=order.id,
                code=code,
                full_code=full_code,
                status="DELIVERED",
                reason=payload.justification,
            )
        )
        db.commit()

        suffix = f": {payload.justification}" if payload.justification else ""
        return ConsumerStatusResponse(
            reasonPhrase=(
                f"{order.id} alterado para '{internal_status}'{suffix}."
            )
        )
