from __future__ import annotations

from typing import Any
from uuid import UUID

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.schemas.order import CheckoutRequest
from app.services.checkout import CheckoutService, CheckoutValidationError


def order_to_dict(order) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "display_id": order.display_id,
        "status": order.status,
        "service_mode": order.service_mode,
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
        **_: Any,
    ) -> ToolResult:
        if not customer_confirmed:
            return ToolResult(
                ok=False,
                error="O cliente ainda não confirmou o resumo final do pedido.",
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
                ),
            )
        except CheckoutValidationError as error:
            return ToolResult(ok=False, error=str(error))

        return ToolResult(ok=True, data=order_to_dict(order))
