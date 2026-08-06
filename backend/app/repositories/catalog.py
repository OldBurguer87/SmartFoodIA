from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import (
    Category,
    ModifierGroup,
    ModifierGroupItem,
    Product,
    ProductModifierGroup,
)
from app.schemas.catalog import ProductCreate


class ProductRepository:
    def create(self, db: Session, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    def list(
        self,
        db: Session,
        *,
        store_id: UUID,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Product]:
        statement: Select[tuple[Product]] = select(Product).where(
            Product.store_id == store_id,
            Product.active.is_(True),
        )
        if query:
            statement = statement.where(Product.name.ilike(f"%{query.strip()}%"))

        statement = statement.order_by(Product.name).limit(limit).offset(offset)
        return list(db.scalars(statement).all())

    def list_active_detailed(
        self,
        db: Session,
        *,
        store_id: UUID,
        delivery: bool | None = None,
        takeout: bool | None = None,
    ) -> list[Product]:
        statement = (
            select(Product)
            .where(Product.store_id == store_id, Product.active.is_(True))
            .options(*self._detail_options())
            .order_by(Product.name)
        )
        if delivery is True:
            statement = statement.where(Product.available_for_delivery.is_(True))
        if takeout is True:
            statement = statement.where(Product.available_for_takeout.is_(True))
        return list(db.scalars(statement).unique().all())

    def get_by_external_code(
        self,
        db: Session,
        *,
        store_id: UUID,
        external_code: str,
    ) -> Product | None:
        statement = select(Product).where(
            Product.store_id == store_id,
            Product.external_code == external_code,
        )
        return db.scalar(statement)

    def get_detailed_by_external_code(
        self,
        db: Session,
        *,
        store_id: UUID,
        external_code: str,
    ) -> Product | None:
        statement = (
            select(Product)
            .where(
                Product.store_id == store_id,
                Product.external_code == external_code,
            )
            .options(*self._detail_options())
        )
        return db.scalar(statement)

    @staticmethod
    def _detail_options():
        return (
            selectinload(Product.category),
            selectinload(Product.modifier_group_links)
            .selectinload(ProductModifierGroup.group)
            .selectinload(ModifierGroup.modifier_links)
            .selectinload(ModifierGroupItem.modifier),
        )
