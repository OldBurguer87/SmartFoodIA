from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.services.catalog.exceptions import ProductNotFoundError
from app.services.catalog.service import CatalogService


def decimal_to_float(value: Decimal) -> float:
    return float(value)


def availability(product, service_mode: str) -> bool:
    if service_mode == "TAKEOUT":
        return product.available_for_takeout
    return product.available_for_delivery


class SearchCatalogTool:
    definition = ToolDefinition(
        name="search_catalog",
        description=(
            "Pesquisa produtos reais da loja por nome, descrição ou categoria. "
            "Nunca cria produtos, preços ou promoções."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2},
                "service_mode": {
                    "type": "string",
                    "enum": ["DELIVERY", "TAKEOUT"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CatalogService()

    def execute(
        self,
        *,
        query: str,
        service_mode: str = "DELIVERY",
        limit: int = 10,
        **_: Any,
    ) -> ToolResult:
        results = self.service.search_products(
            self.context.db,
            store_id=self.context.store_id,
            query=query,
            limit=limit,
            delivery=True if service_mode == "DELIVERY" else None,
            takeout=True if service_mode == "TAKEOUT" else None,
        )
        return ToolResult(
            ok=True,
            data={
                "query": query,
                "products": [
                    {
                        "id": str(result.product.id),
                        "external_code": result.product.external_code,
                        "name": result.product.name,
                        "description": result.product.description,
                        "price": decimal_to_float(result.product.price),
                        "category": result.product.category,
                        "available": availability(
                            result.product,
                            service_mode,
                        ),
                        "relevance_score": result.score,
                    }
                    for result in results
                ],
            },
        )


class GetProductTool:
    definition = ToolDefinition(
        name="get_product",
        description=(
            "Obtém um produto real pelo código PDV e devolve adicionais compatíveis."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "external_code": {"type": "string", "minLength": 1},
                "service_mode": {
                    "type": "string",
                    "enum": ["DELIVERY", "TAKEOUT"],
                },
            },
            "required": ["external_code"],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CatalogService()

    def execute(
        self,
        *,
        external_code: str,
        service_mode: str = "DELIVERY",
        **_: Any,
    ) -> ToolResult:
        try:
            product = self.service.get_by_external_code(
                self.context.db,
                store_id=self.context.store_id,
                external_code=external_code,
            )
        except ProductNotFoundError:
            return ToolResult(
                ok=False,
                error="Produto não encontrado ou indisponível.",
                requires_human=False,
            )

        if not availability(product, service_mode):
            return ToolResult(
                ok=False,
                error=f"Produto indisponível para {service_mode.lower()}.",
                requires_human=False,
            )

        return ToolResult(
            ok=True,
            data={
                "id": str(product.id),
                "external_code": product.external_code,
                "name": product.name,
                "description": product.description,
                "price": decimal_to_float(product.price),
                "category": product.category,
                "available": True,
                "modifier_groups": [
                    {
                        "id": str(group.id),
                        "name": group.name,
                        "description": group.description,
                        "min_select": group.min_select,
                        "max_select": group.max_select,
                        "allow_repeat": group.allow_repeat,
                        "modifiers": [
                            {
                                "id": str(modifier.id),
                                "external_code": modifier.external_code,
                                "name": modifier.name,
                                "description": modifier.description,
                                "price": decimal_to_float(modifier.price),
                                "min_quantity": modifier.min_quantity,
                                "max_quantity": modifier.max_quantity,
                                "default_quantity": modifier.default_quantity,
                            }
                            for modifier in group.modifiers
                        ],
                    }
                    for group in product.modifier_groups
                ],
            },
        )
