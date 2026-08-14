from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.models.catalog import ProductFamily
from app.services.catalog.exceptions import ProductNotFoundError
from app.services.catalog.search import normalize_text, relevance_score
from app.services.catalog.service import CatalogService


def decimal_to_float(value: Decimal) -> float:
    return float(value)


def availability(product, service_mode: str) -> bool:
    if service_mode == "TAKEOUT":
        return product.available_for_takeout
    return product.available_for_delivery



CATALOG_SECTION_TERMS = {
    "MEALS": (
        "prato",
        "pratos",
        "executivo",
        "executivos",
        "refeicao",
        "refeicoes",
        "almoco",
        "jantar",
        "marmita",
    ),
    "BURGERS": (
        "hamburguer",
        "hamburgueres",
        "burger",
        "burguer",
        "lanche",
        "lanches",
        "sanduiche",
    ),
    "DRINKS": (
        "bebida",
        "bebidas",
        "refrigerante",
        "refrigerantes",
        "suco",
        "sucos",
        "agua",
        "cerveja",
        "chopp",
    ),
    "SIDES": (
        "acompanhamento",
        "acompanhamentos",
        "porcao",
        "porcoes",
        "batata",
        "fritas",
    ),
    "DESSERTS": (
        "sobremesa",
        "sobremesas",
        "doce",
        "doces",
    ),
}


def product_matches_section(product, section: str) -> bool:
    if section == "ALL":
        return True

    terms = CATALOG_SECTION_TERMS.get(section, ())

    if not terms:
        return False

    category = normalize_text(product.category)
    name = normalize_text(product.name)
    description = normalize_text(product.description)

    # Categoria tem prioridade. Nome e descrição servem como fallback
    # para catálogos que não possuem categorização perfeita.
    for term in terms:
        normalized_term = normalize_text(term)

        if normalized_term and normalized_term in category:
            return True

    for term in terms:
        normalized_term = normalize_text(term)

        if (
            normalized_term
            and (
                normalized_term in name
                or normalized_term in description
            )
        ):
            return True

    return False


class BrowseCatalogTool:
    definition = ToolDefinition(
        name="browse_catalog",
        description=(
            "Navega pelo cardápio real e disponível da loja, agrupando produtos "
            "por categoria. Use para perguntas amplas como 'o que vocês têm?', "
            "'tem comida?', 'tem almoço?', 'quais bebidas?', 'quais lanches?' "
            "ou quando o cliente quiser ver o cardápio no próprio WhatsApp. "
            "MEALS significa pratos/refeições; BURGERS lanches/hambúrgueres; "
            "DRINKS bebidas; SIDES acompanhamentos/porções; DESSERTS sobremesas; "
            "ALL mostra todas as categorias. Nunca inventa produtos."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": [
                        "ALL",
                        "MEALS",
                        "BURGERS",
                        "DRINKS",
                        "SIDES",
                        "DESSERTS",
                    ],
                },
                "service_mode": {
                    "type": "string",
                    "enum": ["DELIVERY", "TAKEOUT"],
                },
                "max_items_per_category": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.service = CatalogService()

    def execute(
        self,
        *,
        section: str = "ALL",
        service_mode: str = "DELIVERY",
        max_items_per_category: int = 6,
        **_: Any,
    ) -> ToolResult:
        section = (section or "ALL").upper()
        service_mode = service_mode or "DELIVERY"
        max_items_per_category = max_items_per_category or 6

        products = self.service.list_available_products(
            self.context.db,
            store_id=self.context.store_id,
            delivery=True if service_mode == "DELIVERY" else None,
            takeout=True if service_mode == "TAKEOUT" else None,
        )

        filtered = [
            product
            for product in products
            if product_matches_section(product, section)
        ]

        grouped: dict[str, list] = {}

        for product in filtered:
            category = product.category or "Outros"
            grouped.setdefault(category, []).append(product)

        categories = []

        for category_name in sorted(
            grouped,
            key=lambda value: normalize_text(value),
        ):
            category_products = sorted(
                grouped[category_name],
                key=lambda product: (
                    product.price,
                    product.name.casefold(),
                ),
            )

            visible = category_products[:max_items_per_category]

            categories.append(
                {
                    "name": category_name,
                    "product_count": len(category_products),
                    "truncated": (
                        len(category_products)
                        > max_items_per_category
                    ),
                    "products": [
                        {
                            "external_code": product.external_code,
                            "name": product.name,
                            "description": product.description,
                            "price": decimal_to_float(product.price),
                            "available": True,
                        }
                        for product in visible
                    ],
                }
            )

        return ToolResult(
            ok=True,
            data={
                "section": section,
                "service_mode": service_mode,
                "total_products": len(filtered),
                "category_count": len(categories),
                "categories": categories,
            },
        )


class SearchCatalogTool:
    definition = ToolDefinition(
        name="search_catalog",
        description=(
            "Pesquisa produtos reais da loja por nome, descrição ou categoria. "
            "Também retorna famílias de produtos com suas variações vendáveis. "
            "O código da família é apenas agrupador e nunca pode ser usado no pedido. "
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
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                },
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

        family_rows = self.context.db.scalars(
            select(ProductFamily)
            .options(
                selectinload(ProductFamily.products)
            )
            .where(
                ProductFamily.store_id == self.context.store_id,
                ProductFamily.active.is_(True),
            )
        ).all()

        family_results = []

        for family in family_rows:
            score = relevance_score(
                query,
                name=family.name,
                description=family.description,
                category=None,
            )

            if score < 0.15:
                continue

            options = [
                product
                for product in family.products
                if product.active
                and availability(product, service_mode)
            ]

            if not options:
                continue

            options.sort(
                key=lambda product: (
                    product.price,
                    product.name.casefold(),
                )
            )

            family_results.append(
                {
                    # Apenas interno. Nunca deve ser usado no pedido.
                    "family_external_code": family.external_code,
                    "name": family.name,
                    "description": family.description,
                    "selection_name": (
                        family.selection_name or "Opção"
                    ),
                    "selection_required": (
                        family.selection_required
                    ),
                    "relevance_score": score,
                    "options": [
                        {
                            # Este SIM é Código PDV vendável.
                            "external_code": product.external_code,
                            "name": product.name,
                            "price": decimal_to_float(
                                product.price
                            ),
                            "available": True,
                        }
                        for product in options
                    ],
                }
            )

        family_results.sort(
            key=lambda item: (
                -item["relevance_score"],
                item["name"].casefold(),
            )
        )

        selected_families = family_results[:limit]

        # Evita devolver a mesma variação duas vezes:
        # dentro da família e como produto solto.
        family_product_codes = {
            option["external_code"]
            for family in selected_families
            for option in family["options"]
        }

        return ToolResult(
            ok=True,
            data={
                "query": query,
                "families": selected_families,
                "products": [
                    {
                        "id": str(result.product.id),
                        "external_code": (
                            result.product.external_code
                        ),
                        "name": result.product.name,
                        "description": (
                            result.product.description
                        ),
                        "price": decimal_to_float(
                            result.product.price
                        ),
                        "category": result.product.category,
                        "available": availability(
                            result.product,
                            service_mode,
                        ),
                        "relevance_score": result.score,
                    }
                    for result in results
                    if (
                        result.product.external_code
                        not in family_product_codes
                    )
                ],
            },
        )


class GetProductTool:
    definition = ToolDefinition(
        name="get_product",
        description=(
            "Obtém um produto real pelo código PDV e devolve "
            "adicionais compatíveis."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "external_code": {
                    "type": "string",
                    "minLength": 1,
                },
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
                error=(
                    f"Produto indisponível para "
                    f"{service_mode.lower()}."
                ),
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
                                "external_code": (
                                    modifier.external_code
                                ),
                                "name": modifier.name,
                                "description": (
                                    modifier.description
                                ),
                                "price": decimal_to_float(
                                    modifier.price
                                ),
                                "min_quantity": (
                                    modifier.min_quantity
                                ),
                                "max_quantity": (
                                    modifier.max_quantity
                                ),
                                "default_quantity": (
                                    modifier.default_quantity
                                ),
                            }
                            for modifier in group.modifiers
                        ],
                    }
                    for group in product.modifier_groups
                ],
            },
        )
