from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("store_id", "display_id", name="uq_order_store_display_id"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    display_id: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PLACED", index=True)
    service_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    change_for: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    address_street: Mapped[str | None] = mapped_column(String(180))
    address_number: Mapped[str | None] = mapped_column(String(30))
    address_neighborhood: Mapped[str | None] = mapped_column(String(120))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_state: Mapped[str | None] = mapped_column(String(2))
    address_postal_code: Mapped[str | None] = mapped_column(String(12))
    address_complement: Mapped[str | None] = mapped_column(String(180))
    address_reference: Mapped[str | None] = mapped_column(String(240))
    consumer_order_id: Mapped[str | None] = mapped_column(String(80))

    # Horário prometido ao cliente em pedidos agendados.
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # Momento a partir do qual o Consumer pode receber o pedido.
    release_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_items"

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_external_code: Mapped[str] = mapped_column(String(80), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    observations: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="items")
    modifiers: Mapped[list["OrderItemModifier"]] = relationship(
        back_populates="order_item",
        cascade="all, delete-orphan",
    )


class OrderItemModifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_item_modifiers"

    order_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    modifier_id: Mapped[UUID] = mapped_column(
        ForeignKey("modifiers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    modifier_external_code: Mapped[str] = mapped_column(String(80), nullable=False)
    modifier_name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order_item: Mapped[OrderItem] = relationship(back_populates="modifiers")


class OrderEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "order_events"

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    full_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))

    order: Mapped[Order] = relationship(back_populates="events")
