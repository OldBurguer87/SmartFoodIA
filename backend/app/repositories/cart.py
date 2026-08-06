from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.cart import Cart, CartItem


class CartRepository:
    def get(self, db: Session, cart_id: UUID) -> Cart | None:
        statement = (
            select(Cart)
            .where(Cart.id == cart_id)
            .options(
                selectinload(Cart.items).selectinload(CartItem.modifiers),
            )
        )
        return db.scalar(statement)

    def get_open_for_customer(
        self,
        db: Session,
        *,
        store_id: UUID,
        customer_id: UUID,
    ) -> Cart | None:
        statement = (
            select(Cart)
            .where(
                Cart.store_id == store_id,
                Cart.customer_id == customer_id,
                Cart.status == "OPEN",
            )
            .options(selectinload(Cart.items).selectinload(CartItem.modifiers))
            .order_by(Cart.created_at.desc())
        )
        return db.scalars(statement).first()

    def create(
        self,
        db: Session,
        *,
        store_id: UUID,
        customer_id: UUID,
        service_mode: str,
    ) -> Cart:
        cart = Cart(
            store_id=store_id,
            customer_id=customer_id,
            service_mode=service_mode,
            status="OPEN",
        )
        db.add(cart)
        db.commit()
        return self.get(db, cart.id)
