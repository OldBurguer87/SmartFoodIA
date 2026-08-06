from __future__ import annotations

from typing import Any
from uuid import UUID

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.schemas.cart import (
    CartItemAdd,
    CartItemUpdate,
    ModifierSelection,
)
from app.services.cart import CartNotFoundError, CartService, CartValidationError


def cart_to_dict(cart) -> dict[str, Any]:
    return {
        "id": str(cart.id),
        "store_id": str(cart.store_id),
        "customer_id": str(cart.customer_id),
        "status": cart.status,
        "service_mode": cart.service_mode,
        "subtotal": float(cart.subtotal),
        "items": [
            {
                "id": str(item.id),
                "product_external_code": item.product_external_code,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "observations": item.observations,
                "total": float(item.total),
                "modifiers": [
                    {
                        "id": str(modifier.id),
                        "external_code": modifier.external_code,
                        "name": modifier.name,
                        "quantity": modifier.quantity,
                        "unit_price": float(modifier.unit_price),
                        "total": float(modifier.total),
                    }
                    for modifier in item.modifiers
                ],
            }
            for item in cart.items
        ],
    }


class GetOrCreateCartTool:
    definition = ToolDefinition(
        name="get_or_create_cart",
        description="Cria ou recupera o carrinho aberto do cliente.",
        input_schema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "format": "uuid"},
                "service_mode": {
                    "type": "string",
                    "enum": ["DELIVERY", "TAKEOUT"],
                },
            },
            "required": ["customer_id", "service_mode"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CartService()

    def execute(
        self,
        *,
        customer_id: str,
        service_mode: str,
        **_: Any,
    ) -> ToolResult:
        try:
            cart = self.service.create_or_get_open(
                self.context.db,
                store_id=self.context.store_id,
                customer_id=UUID(customer_id),
                service_mode=service_mode,
            )
        except CartValidationError as error:
            return ToolResult(ok=False, error=str(error))
        return ToolResult(ok=True, data=cart_to_dict(cart))


class AddCartItemTool:
    definition = ToolDefinition(
        name="add_cart_item",
        description=(
            "Adiciona um produto real ao carrinho e valida complementos compatíveis."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "cart_id": {"type": "string", "format": "uuid"},
                "product_external_code": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                "observations": {"type": ["string", "null"]},
                "modifiers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "external_code": {"type": "string"},
                            "quantity": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 20,
                            },
                        },
                        "required": ["external_code", "quantity"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["cart_id", "product_external_code"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CartService()

    def execute(
        self,
        *,
        cart_id: str,
        product_external_code: str,
        quantity: int = 1,
        observations: str | None = None,
        modifiers: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> ToolResult:
        try:
            cart = self.service.add_item(
                self.context.db,
                cart_id=UUID(cart_id),
                payload=CartItemAdd(
                    product_external_code=product_external_code,
                    quantity=quantity,
                    observations=observations,
                    modifiers=[
                        ModifierSelection(**modifier)
                        for modifier in (modifiers or [])
                    ],
                ),
            )
        except (CartNotFoundError, CartValidationError) as error:
            return ToolResult(
                ok=False,
                error=str(error),
                requires_human=False,
            )
        return ToolResult(ok=True, data=cart_to_dict(cart))


class UpdateCartItemTool:
    definition = ToolDefinition(
        name="update_cart_item",
        description="Altera quantidade ou observação de um item do carrinho.",
        input_schema={
            "type": "object",
            "properties": {
                "cart_id": {"type": "string", "format": "uuid"},
                "item_id": {"type": "string", "format": "uuid"},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                "observations": {"type": ["string", "null"]},
            },
            "required": ["cart_id", "item_id", "quantity"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CartService()

    def execute(
        self,
        *,
        cart_id: str,
        item_id: str,
        quantity: int,
        observations: str | None = None,
        **_: Any,
    ) -> ToolResult:
        try:
            cart = self.service.update_item(
                self.context.db,
                cart_id=UUID(cart_id),
                item_id=UUID(item_id),
                payload=CartItemUpdate(
                    quantity=quantity,
                    observations=observations,
                ),
            )
        except (CartNotFoundError, CartValidationError) as error:
            return ToolResult(ok=False, error=str(error))
        return ToolResult(ok=True, data=cart_to_dict(cart))


class RemoveCartItemTool:
    definition = ToolDefinition(
        name="remove_cart_item",
        description="Remove um item do carrinho.",
        input_schema={
            "type": "object",
            "properties": {
                "cart_id": {"type": "string", "format": "uuid"},
                "item_id": {"type": "string", "format": "uuid"},
            },
            "required": ["cart_id", "item_id"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CartService()

    def execute(
        self,
        *,
        cart_id: str,
        item_id: str,
        **_: Any,
    ) -> ToolResult:
        try:
            cart = self.service.remove_item(
                self.context.db,
                cart_id=UUID(cart_id),
                item_id=UUID(item_id),
            )
        except (CartNotFoundError, CartValidationError) as error:
            return ToolResult(ok=False, error=str(error))
        return ToolResult(ok=True, data=cart_to_dict(cart))


class GetCartTool:
    definition = ToolDefinition(
        name="get_cart",
        description="Consulta o carrinho atual e seus valores calculados pelo Core.",
        input_schema={
            "type": "object",
            "properties": {
                "cart_id": {"type": "string", "format": "uuid"},
            },
            "required": ["cart_id"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CartService()

    def execute(self, *, cart_id: str, **_: Any) -> ToolResult:
        try:
            cart = self.service.get(self.context.db, UUID(cart_id))
        except CartNotFoundError as error:
            return ToolResult(ok=False, error=str(error))
        return ToolResult(ok=True, data=cart_to_dict(cart))
