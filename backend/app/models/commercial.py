from datetime import time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreCommercialRules(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_commercial_rules"
    __table_args__ = (UniqueConstraint("store_id", name="uq_store_commercial_rules_store"),)

    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    manual_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pause_reason: Mapped[str | None] = mapped_column(String(240))
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    takeout_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    minimum_delivery_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    delivery_fee_mode: Mapped[str] = mapped_column(String(20), default="FIXED", nullable=False)
    fixed_delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    accepts_pix: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Dados oficiais usados para validar comprovantes PIX.
    pix_receiver_name: Mapped[str | None] = mapped_column(String(180))
    pix_receiver_document: Mapped[str | None] = mapped_column(String(40))
    pix_key: Mapped[str | None] = mapped_column(String(200))
    pix_receiver_institution: Mapped[str | None] = mapped_column(String(180))

    pix_auto_verify_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    pix_receipt_max_age_minutes: Mapped[int] = mapped_column(
        Integer,
        default=360,
        nullable=False,
    )

    pix_amount_tolerance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.01"),
        nullable=False,
    )
    accepts_credit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accepts_debit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accepts_cash: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_change: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    average_prep_minutes: Mapped[int | None] = mapped_column(Integer)
    general_notes: Mapped[str | None] = mapped_column(Text)
    menu_original_name: Mapped[str | None] = mapped_column(String(240))
    menu_storage_name: Mapped[str | None] = mapped_column(String(240))
    menu_public_token: Mapped[str | None] = mapped_column(String(64), unique=True)


class StoreBusinessHours(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_business_hours"
    __table_args__ = (UniqueConstraint("store_id", "weekday", name="uq_store_business_hours_day"),)

    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    delivery_until: Mapped[time | None] = mapped_column(Time)
    takeout_until: Mapped[time | None] = mapped_column(Time)


class StoreDeliveryZone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_delivery_zones"
    __table_args__ = (UniqueConstraint("store_id", "normalized_name", name="uq_store_delivery_zone_name"),)

    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(140), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    delivery_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
