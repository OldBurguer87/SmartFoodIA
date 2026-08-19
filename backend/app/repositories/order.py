from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order, OrderEvent, OrderItem
from app.models.payment import PaymentReceipt


class OrderRepository:
    def get(self, db: Session, order_id: UUID) -> Order | None:
        statement = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.events),
            )
        )
        return db.scalar(statement)

    def get_for_store(
        self,
        db: Session,
        *,
        store_id: UUID,
        order_id: UUID,
    ) -> Order | None:
        statement = (
            select(Order)
            .where(Order.id == order_id, Order.store_id == store_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.events),
            )
        )
        return db.scalar(statement)

    def get_by_cart(self, db: Session, cart_id: UUID) -> Order | None:
        statement = (
            select(Order)
            .where(Order.cart_id == cart_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.events),
            )
        )
        return db.scalar(statement)

    def next_display_id(self, db: Session, store_id: UUID) -> str:
        count = db.scalar(
            select(func.count(Order.id)).where(Order.store_id == store_id)
        ) or 0
        return str(count + 1).zfill(6)

    def list_pending_events(
        self,
        db: Session,
        *,
        store_id: UUID,
        limit: int = 100,
    ) -> list[OrderEvent]:
        statement = (
            select(OrderEvent)
            .join(Order, Order.id == OrderEvent.order_id)
            .where(
                OrderEvent.status == "PENDING",
                Order.store_id == store_id,
                or_(
                    Order.release_at.is_(None),
                    Order.release_at <= func.now(),
                ),
                or_(
                    Order.payment_method != "PIX",
                    ~Order.service_mode.in_(["DELIVERY", "TAKEOUT"]),
                    select(PaymentReceipt.id)
                    .where(
                        PaymentReceipt.store_id == Order.store_id,
                        PaymentReceipt.order_id == Order.id,
                        PaymentReceipt.status.in_(
                            ["AUTO_CONFIRMED", "HUMAN_CONFIRMED"]
                        ),
                    )
                    .exists(),
                ),
            )
            .order_by(OrderEvent.created_at)
            .limit(limit)
        )
        return list(db.scalars(statement).all())
