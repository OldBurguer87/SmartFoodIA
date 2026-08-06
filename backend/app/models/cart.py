from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Cart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "carts"

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    service_mode: Mapped[str] = mapped_column(
        String(20),
        default="DELIVERY",
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship(back_populates="carts")
    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart",
        cascade="all, delete-orphan",
    )


class CartItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cart_items"

    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"),
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
    observations: Mapped[str | None] = mapped_column(Text)

    cart: Mapped[Cart] = relationship(back_populates="items")
    modifiers: Mapped[list["CartItemModifier"]] = relationship(
        back_populates="cart_item",
        cascade="all, delete-orphan",
    )


class CartItemModifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cart_item_modifiers"
    __table_args__ = (
        UniqueConstraint(
            "cart_item_id",
            "modifier_id",
            name="uq_cart_item_modifier",
        ),
    )

    cart_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("cart_items.id", ondelete="CASCADE"),
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

    cart_item: Mapped[CartItem] = relationship(back_populates="modifiers")


from app.models.customer import Customer  # noqa: E402
