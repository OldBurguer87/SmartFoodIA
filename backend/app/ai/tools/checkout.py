from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.models.conversation import AIEvent
from app.models.customer import CustomerAddress
from app.schemas.order import CheckoutRequest
from app.services.checkout import CheckoutService, CheckoutValidationError


def order_to_dict(order) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "display_id": order.display_id,
        "status": order.status,
        "service_mode": order.service_mode,
        "scheduled_for": (
            order.scheduled_for.isoformat()
            if order.scheduled_for is not None
            else None
        ),
        "payment_method": order.payment_method,
        "payment_type": order.payment_type,
        "change_for": float(order.change_for) if order.change_for is not None else None,
        "subtotal": float(order.subtotal),
        "delivery_fee": float(order.delivery_fee),
        "discount": float(order.discount),
        "total": float(order.total),
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "address": (
            {
                "street": order.address.street,
                "number": order.address.number,
                "neighborhood": order.address.neighborhood,
                "city": order.address.city,
                "state": order.address.state,
                "postal_code": order.address.postal_code,
                "complement": order.address.complement,
                "reference": order.address.reference,
            }
            if order.address is not None
            else None
        ),
        "items": [
            {
                "id": str(item.id),
                "external_code": item.external_code,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "total_price": float(item.total_price),
                "observations": item.observations,
                "modifiers": [
                    {
                        "external_code": modifier.external_code,
                        "name": modifier.name,
                        "quantity": modifier.quantity,
                        "unit_price": float(modifier.unit_price),
                        "total_price": float(modifier.total_price),
                    }
                    for modifier in item.modifiers
                ],
            }
            for item in order.items
        ],
    }


class CheckoutCartTool:
    definition = ToolDefinition(
        name="checkout_cart",
        description=(
            "Finaliza um carrinho confirmado pelo cliente. "
            "Só deve ser usado após resumo e confirmação explícita."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "cart_id": {"type": "string", "format": "uuid"},
                "address_id": {
                    "type": ["string", "null"],
                    "format": "uuid",
                },
                "payment_method": {
                    "type": "string",
                    "enum": ["PIX", "CREDIT", "DEBIT", "CASH"],
                },
                "payment_type": {
                    "type": "string",
                    "enum": ["PENDING", "PREPAID"],
                },
                "change_for": {"type": ["number", "null"], "minimum": 0},
                "delivery_fee": {"type": "number", "minimum": 0},
                "discount": {"type": "number", "minimum": 0},
                "scheduled_for": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": (
                        "Data e hora agendada em ISO 8601. "
                        "Use null para pedido imediato."
                    ),
                },
                "customer_confirmed": {"type": "boolean"},
            },
            "required": [
                "cart_id",
                "payment_method",
                "customer_confirmed",
            ],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CheckoutService()

    _DUPLICATE_CHECKOUT_WINDOW = timedelta(minutes=2)

    @staticmethod
    def _normalized_text(value: str | None) -> str:
        return " ".join(str(value or "").split()).casefold()

    @staticmethod
    def _money(value) -> str:
        return str(
            Decimal(str(value)).quantize(Decimal("0.01"))
        )

    @classmethod
    def _items_signature(cls, items) -> tuple:
        grouped = {}

        for item in items:
            modifiers = tuple(
                sorted(
                    (
                        str(modifier.modifier_external_code),
                        int(modifier.quantity),
                        cls._money(modifier.unit_price),
                    )
                    for modifier in item.modifiers
                )
            )

            key = (
                str(item.product_external_code),
                cls._money(item.unit_price),
                cls._normalized_text(item.observations),
                modifiers,
            )

            grouped[key] = (
                grouped.get(key, 0)
                + int(item.quantity)
            )

        return tuple(
            sorted(
                (key, quantity)
                for key, quantity in grouped.items()
            )
        )

    @staticmethod
    def _same_optional_money(previous, requested) -> bool:
        if previous is None and requested is None:
            return True

        if previous is None or requested is None:
            return False

        return Decimal(str(previous)).quantize(
            Decimal("0.01")
        ) == Decimal(str(requested)).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _same_schedule(previous, requested) -> bool:
        if previous is None and requested is None:
            return True

        if previous is None or requested is None:
            return False

        try:
            previous_dt = datetime.fromisoformat(
                str(previous).replace("Z", "+00:00")
            )
            requested_dt = datetime.fromisoformat(
                str(requested).replace("Z", "+00:00")
            )

            if (
                previous_dt.tzinfo is not None
                and requested_dt.tzinfo is not None
            ):
                previous_dt = previous_dt.astimezone(
                    timezone.utc
                )
                requested_dt = requested_dt.astimezone(
                    timezone.utc
                )

            return previous_dt == requested_dt
        except ValueError:
            return str(previous) == str(requested)

    def _same_delivery_address(
        self,
        db,
        *,
        cart,
        order,
        address_id: str | None,
    ) -> bool:
        if cart.service_mode != "DELIVERY":
            return True

        if not address_id:
            return False

        try:
            parsed_address_id = UUID(str(address_id))
        except (TypeError, ValueError):
            return False

        address = db.scalar(
            select(CustomerAddress).where(
                CustomerAddress.id == parsed_address_id,
                CustomerAddress.customer_id == cart.customer_id,
                CustomerAddress.active.is_(True),
            )
        )

        if address is None:
            return False

        current = (
            address.street,
            address.number,
            address.neighborhood,
            address.city,
            address.state,
            address.postal_code,
            address.complement,
            address.reference,
        )

        previous = (
            order.address_street,
            order.address_number,
            order.address_neighborhood,
            order.address_city,
            order.address_state,
            order.address_postal_code,
            order.address_complement,
            order.address_reference,
        )

        return tuple(
            self._normalized_text(value)
            for value in current
        ) == tuple(
            self._normalized_text(value)
            for value in previous
        )

    def _find_recent_duplicate_order(
        self,
        db,
        *,
        cart_id: UUID,
        address_id: str | None,
        payment_method: str,
        payment_type: str,
        change_for: float | None,
        discount: float,
        scheduled_for: str | None,
    ):
        conversation_id = self.context.conversation_id

        if conversation_id is None:
            return None

        cutoff = (
            datetime.now(timezone.utc)
            - self._DUPLICATE_CHECKOUT_WINDOW
        )

        event = db.scalar(
            select(AIEvent)
            .where(
                AIEvent.store_id == self.context.store_id,
                AIEvent.conversation_id == conversation_id,
                AIEvent.event_type == "TOOL_EXECUTION",
                AIEvent.tool_name == "checkout_cart",
                AIEvent.success.is_(True),
                AIEvent.created_at >= cutoff,
            )
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        if event is None:
            return None

        payload = event.payload_json or {}
        result = payload.get("result") or {}
        previous_data = result.get("data") or {}

        if not result.get("ok", False):
            return None

        raw_order_id = previous_data.get("id")

        if not raw_order_id:
            return None

        try:
            order_id = UUID(str(raw_order_id))
        except (TypeError, ValueError):
            return None

        order = self.service.order_repository.get_for_store(
            db,
            store_id=self.context.store_id,
            order_id=order_id,
        )

        cart = self.service.cart_repository.get(
            db,
            cart_id,
        )

        if order is None or cart is None:
            return None

        if cart.status != "OPEN":
            return None

        if order.status == "CANCELLED":
            return None

        if cart.store_id != self.context.store_id:
            return None

        if order.customer_id != cart.customer_id:
            return None

        if order.service_mode != cart.service_mode:
            return None

        if order.payment_method != payment_method:
            return None

        if order.payment_type != payment_type:
            return None

        if Decimal(str(order.discount)).quantize(
            Decimal("0.01")
        ) != Decimal(str(discount)).quantize(
            Decimal("0.01")
        ):
            return None

        if not self._same_optional_money(
            order.change_for,
            change_for,
        ):
            return None

        if not self._same_schedule(
            previous_data.get("scheduled_for"),
            scheduled_for,
        ):
            return None

        if not self._same_delivery_address(
            db,
            cart=cart,
            order=order,
            address_id=address_id,
        ):
            return None

        if self._items_signature(
            cart.items
        ) != self._items_signature(
            order.items
        ):
            return None

        return order

    def _discard_duplicate_cart(
        self,
        db,
        *,
        cart_id: UUID,
    ) -> None:
        cart = self.service.cart_repository.get(
            db,
            cart_id,
        )

        if cart is None or cart.status != "OPEN":
            return

        # O carrinho reconstruído pela IA não representa um novo pedido.
        # Esvaziá-lo evita que os mesmos itens contaminem o próximo pedido.
        for item in list(cart.items):
            db.delete(item)

        db.commit()

    def execute(
        self,
        *,
        cart_id: str,
        payment_method: str,
        customer_confirmed: bool,
        address_id: str | None = None,
        payment_type: str = "PENDING",
        change_for: float | None = None,
        delivery_fee: float = 0,
        discount: float = 0,
        scheduled_for: str | None = None,
        **_: Any,
    ) -> ToolResult:
        if not customer_confirmed:
            return ToolResult(
                ok=False,
                error="O cliente ainda não confirmou o resumo final do pedido.",
            )

        duplicate_order = self._find_recent_duplicate_order(
            self.context.db,
            cart_id=UUID(cart_id),
            address_id=address_id,
            payment_method=payment_method,
            payment_type=payment_type,
            change_for=change_for,
            discount=discount,
            scheduled_for=scheduled_for,
        )

        if duplicate_order is not None:
            self._discard_duplicate_cart(
                self.context.db,
                cart_id=UUID(cart_id),
            )

            persisted = self.service.get(
                self.context.db,
                duplicate_order.id,
            )

            return ToolResult(
                ok=True,
                data=order_to_dict(persisted),
            )

        try:
            order = self.service.checkout(
                self.context.db,
                cart_id=UUID(cart_id),
                payload=CheckoutRequest(
                    address_id=UUID(address_id) if address_id else None,
                    payment_method=payment_method,
                    payment_type=payment_type,
                    change_for=change_for,
                    delivery_fee=delivery_fee,
                    discount=discount,
                    scheduled_for=scheduled_for,
                ),
            )
        except CheckoutValidationError as error:
            return ToolResult(ok=False, error=str(error))

        return ToolResult(ok=True, data=order_to_dict(order))
