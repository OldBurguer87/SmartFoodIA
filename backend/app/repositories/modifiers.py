from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Modifier, ModifierGroup, ModifierGroupItem, ProductModifierGroup
from app.schemas.modifiers import (
    ModifierCreate,
    ModifierGroupCreate,
    ModifierGroupItemCreate,
    ProductModifierGroupCreate,
)


class ModifierRepository:
    def create_group(self, db: Session, data: ModifierGroupCreate) -> ModifierGroup:
        group = ModifierGroup(**data.model_dump())
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    def list_groups(self, db: Session, store_id) -> list[ModifierGroup]:
        statement = (
            select(ModifierGroup)
            .where(ModifierGroup.store_id == store_id, ModifierGroup.active.is_(True))
            .order_by(ModifierGroup.display_order, ModifierGroup.name)
        )
        return list(db.scalars(statement).all())

    def create_modifier(self, db: Session, data: ModifierCreate) -> Modifier:
        modifier = Modifier(**data.model_dump())
        db.add(modifier)
        db.commit()
        db.refresh(modifier)
        return modifier

    def list_modifiers(self, db: Session, store_id) -> list[Modifier]:
        statement = (
            select(Modifier)
            .where(Modifier.store_id == store_id, Modifier.active.is_(True))
            .order_by(Modifier.name)
        )
        return list(db.scalars(statement).all())

    def attach_group_to_product(
        self, db: Session, data: ProductModifierGroupCreate
    ) -> ProductModifierGroup:
        link = ProductModifierGroup(**data.model_dump())
        db.add(link)
        db.commit()
        db.refresh(link)
        return link

    def add_modifier_to_group(
        self, db: Session, data: ModifierGroupItemCreate
    ) -> ModifierGroupItem:
        link = ModifierGroupItem(**data.model_dump())
        db.add(link)
        db.commit()
        db.refresh(link)
        return link
