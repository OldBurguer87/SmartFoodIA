from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentReceipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_receipts"

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    channel_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("channel_events.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    external_media_id: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    media_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    mime_type: Mapped[str | None] = mapped_column(String(120))
    original_filename: Mapped[str | None] = mapped_column(String(240))

    storage_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    transaction_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
    )

    retention_purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="RECEIVED",
        nullable=False,
        index=True,
    )

    extracted_receiver_name: Mapped[str | None] = mapped_column(String(180))
    extracted_receiver_document: Mapped[str | None] = mapped_column(String(40))
    extracted_pix_key: Mapped[str | None] = mapped_column(String(200))

    extracted_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2)
    )

    extracted_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    extracted_transaction_id: Mapped[str | None] = mapped_column(
        String(200),
        index=True,
    )

    extracted_transaction_status: Mapped[str | None] = mapped_column(
        String(100)
    )

    extracted_payer_name: Mapped[str | None] = mapped_column(String(180))
    extracted_institution: Mapped[str | None] = mapped_column(String(180))

    ai_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4)
    )

    validation_json: Mapped[dict | None] = mapped_column(JSON)

    reviewed_by: Mapped[str | None] = mapped_column(String(160))

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    review_notes: Mapped[str | None] = mapped_column(Text)
