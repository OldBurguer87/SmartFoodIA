from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.catalog import ModifierGroup, Product
from app.repositories.catalog import ProductRepository
from app.services.catalog.dto import (
    ModifierDTO,
    ModifierGroupDTO,
    ProductDTO,
    ProductSearchResultDTO,
)
from app.services.catalog.exceptions import ProductNotFoundError
from app.services.catalog.search import relevance_score


class CatalogService:
    def __init__(self, repository: ProductRepository | None = None) -> None:
        self.repository = repository or ProductRepository()

    def get_by_external_code(
        self,
        db: Session,
        *,
        store_id: UUID,
        external_code: str,
    ) -> ProductDTO:
        product = self.repository.get_detailed_by_external_code(
            db,
            store_id=store_id,
            external_code=external_code.strip(),
        )
        if product is None or not product.active:
            raise ProductNotFoundError(external_code)
        return self._to_product_dto(product)

    def search_products(
        self,
        db: Session,
        *,
        store_id: UUID,
        query: str,
        limit: int = 10,
        delivery: bool | None = None,
        takeout: bool | None = None,
        minimum_score: float = 0.15,
    ) -> list[ProductSearchResultDTO]:
        products = self.repository.list_active_detailed(
            db,
            store_id=store_id,
            delivery=delivery,
            takeout=takeout,
        )
        results: list[ProductSearchResultDTO] = []
        for product in products:
            score = relevance_score(
                query,
                name=product.name,
                description=product.description,
                category=product.category.name if product.category else None,
            )
            if score >= minimum_score:
                results.append(
                    ProductSearchResultDTO(
                        product=self._to_product_dto(product),
                        score=score,
                    )
                )
        results.sort(key=lambda item: (-item.score, item.product.name.casefold()))
        return results[:limit]

    def find_best_product(
        self,
        db: Session,
        *,
        store_id: UUID,
        query: str,
        minimum_score: float = 0.72,
    ) -> ProductDTO:
        results = self.search_products(
            db,
            store_id=store_id,
            query=query,
            limit=1,
            minimum_score=minimum_score,
        )
        if not results:
            raise ProductNotFoundError(query)
        return results[0].product

    def list_available_products(
        self,
        db: Session,
        *,
        store_id: UUID,
        delivery: bool | None = None,
        takeout: bool | None = None,
    ) -> list[ProductDTO]:
        return [
            self._to_product_dto(product)
            for product in self.repository.list_active_detailed(
                db,
                store_id=store_id,
                delivery=delivery,
                takeout=takeout,
            )
        ]

    def _to_product_dto(self, product: Product) -> ProductDTO:
        links = sorted(
            product.modifier_group_links,
            key=lambda link: (link.display_order, link.group.display_order, link.group.name),
        )
        groups = tuple(
            self._to_group_dto(
                link.group,
                min_select=link.min_select_override,
                max_select=link.max_select_override,
            )
            for link in links
            if link.group.active
        )
        return ProductDTO(
            id=product.id,
            store_id=product.store_id,
            external_code=product.external_code,
            name=product.name,
            description=product.description,
            price=product.price,
            category=product.category.name if product.category else None,
            available_for_delivery=product.available_for_delivery,
            available_for_takeout=product.available_for_takeout,
            modifier_groups=groups,
        )

    @staticmethod
    def _to_group_dto(
        group: ModifierGroup,
        *,
        min_select: int | None,
        max_select: int | None,
    ) -> ModifierGroupDTO:
        links = sorted(
            group.modifier_links,
            key=lambda link: (link.display_order, link.modifier.name.casefold()),
        )
        modifiers = tuple(
            ModifierDTO(
                id=link.modifier.id,
                external_code=link.modifier.external_code,
                name=link.modifier.name,
                description=link.modifier.description,
                price=link.modifier.price,
                min_quantity=link.min_quantity,
                max_quantity=link.max_quantity,
                default_quantity=link.default_quantity,
                display_order=link.display_order,
            )
            for link in links
            if link.modifier.active
        )
        return ModifierGroupDTO(
            id=group.id,
            name=group.name,
            description=group.description,
            min_select=group.min_select if min_select is None else min_select,
            max_select=group.max_select if max_select is None else max_select,
            allow_repeat=group.allow_repeat,
            display_order=group.display_order,
            modifiers=modifiers,
        )
