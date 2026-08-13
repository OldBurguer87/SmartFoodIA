from uuid import UUID

from sqlalchemy import ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreMenuDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_menu_documents"
    __table_args__ = (UniqueConstraint("store_id", name="uq_store_menu_document_store"),)

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(240), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), default="application/pdf", nullable=False)
    public_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
