from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stores: Mapped[list["Store"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Store(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stores"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    city: Mapped[str] = mapped_column(String(100), default="Coari", nullable=False)
    state: Mapped[str] = mapped_column(String(2), default="AM", nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50), default="America/Manaus", nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped[Company] = relationship(back_populates="stores")
    categories: Mapped[list["Category"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )
    modifier_groups: Mapped[list["ModifierGroup"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )
    modifiers: Mapped[list["Modifier"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("store_id", "name", name="uq_category_store_name"),)

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    store: Mapped[Store] = relationship(back_populates="categories")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("store_id", "external_code", name="uq_product_store_external_code"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    external_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    available_for_delivery: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    available_for_takeout: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    store: Mapped[Store] = relationship(back_populates="products")
    category: Mapped[Category | None] = relationship(back_populates="products")
    modifier_group_links: Mapped[list["ProductModifierGroup"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ModifierGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (
        UniqueConstraint("store_id", "name", name="uq_modifier_group_store_name"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    min_select: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_select: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    allow_repeat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    store: Mapped[Store] = relationship(back_populates="modifier_groups")
    modifier_links: Mapped[list["ModifierGroupItem"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    product_links: Mapped[list["ProductModifierGroup"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Modifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "modifiers"
    __table_args__ = (
        UniqueConstraint("store_id", "external_code", name="uq_modifier_store_external_code"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    external_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    store: Mapped[Store] = relationship(back_populates="modifiers")
    group_links: Mapped[list["ModifierGroupItem"]] = relationship(
        back_populates="modifier", cascade="all, delete-orphan"
    )


class ProductModifierGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_modifier_groups"
    __table_args__ = (
        UniqueConstraint("product_id", "modifier_group_id", name="uq_product_modifier_group"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    modifier_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_select_override: Mapped[int | None] = mapped_column(Integer)
    max_select_override: Mapped[int | None] = mapped_column(Integer)

    product: Mapped[Product] = relationship(back_populates="modifier_group_links")
    group: Mapped[ModifierGroup] = relationship(back_populates="product_links")


class ModifierGroupItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "modifier_group_items"
    __table_args__ = (
        UniqueConstraint("modifier_group_id", "modifier_id", name="uq_modifier_group_item"),
    )

    modifier_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False
    )
    modifier_id: Mapped[UUID] = mapped_column(
        ForeignKey("modifiers.id", ondelete="CASCADE"), nullable=False
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    default_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped[ModifierGroup] = relationship(back_populates="modifier_links")
    modifier: Mapped[Modifier] = relationship(back_populates="group_links")
