from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_integrations"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "provider",
            name="uq_store_integration_provider",
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
