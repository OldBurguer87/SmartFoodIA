from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreCatalogConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "store_catalog_configs"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            name="uq_store_catalog_config_store",
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Exemplos:
    # CONSUMER, GENERIC, FUTURE_PROVIDER
    provider: Mapped[str] = mapped_column(
        String(40),
        default="GENERIC",
        nullable=False,
    )

    # Exemplos:
    # XLSX, PRODCON, API, FULL_XLSX
    products_source: Mapped[str | None] = mapped_column(String(30))
    complements_source: Mapped[str | None] = mapped_column(String(30))
    relations_source: Mapped[str | None] = mapped_column(String(30))


class CatalogVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_versions"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "version_code",
            name="uq_catalog_version_store_code",
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Ex.: CAT-20260813-001
    version_code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    # DRAFT / IMPORTING / ACTIVE / FAILED / ARCHIVED
    status: Mapped[str] = mapped_column(
        String(20),
        default="DRAFT",
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    products_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    modifiers_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    relations_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    notes: Mapped[str | None] = mapped_column(Text)


class CatalogSourceFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_source_files"
    __table_args__ = (
        UniqueConstraint(
            "catalog_version_id",
            "role",
            name="uq_catalog_source_file_version_role",
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )

    catalog_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalog_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # MAIN / COMPLEMENTS / PRODCON / FULL
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # XLSX / PRODCON
    source_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    original_name: Mapped[str] = mapped_column(
        String(240),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    # Evita importar acidentalmente o mesmo arquivo como uma versão diferente.
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    content: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
