from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.catalog_version import (
    CatalogSourceFile,
    CatalogVersion,
    StoreCatalogConfig,
)


class CatalogVersioningService:
    def get_or_create_config(
        self,
        db: Session,
        *,
        store_id: UUID,
        provider: str = "GENERIC",
    ) -> StoreCatalogConfig:
        config = db.scalar(
            select(StoreCatalogConfig).where(
                StoreCatalogConfig.store_id == store_id
            )
        )

        if config is None:
            config = StoreCatalogConfig(
                store_id=store_id,
                provider=provider.upper(),
            )
            db.add(config)
            db.flush()

        return config

    def create_version(
        self,
        db: Session,
        *,
        store_id: UUID,
        provider: str,
    ) -> CatalogVersion:
        store = db.get(Store, store_id)
        if store is None:
            raise ValueError("Loja não encontrada.")

        version = CatalogVersion(
            store_id=store_id,
            version_code=self._next_version_code(db, store_id),
            provider=provider.upper(),
            status="DRAFT",
            active=False,
        )

        db.add(version)
        db.flush()
        return version

    def save_source_file(
        self,
        db: Session,
        *,
        store_id: UUID,
        catalog_version_id: UUID,
        role: str,
        source_format: str,
        original_name: str,
        content_type: str,
        content: bytes,
    ) -> CatalogSourceFile:
        version = db.scalar(
            select(CatalogVersion).where(
                CatalogVersion.id == catalog_version_id,
                CatalogVersion.store_id == store_id,
            )
        )

        if version is None:
            raise ValueError("Versão do catálogo não encontrada.")

        normalized_role = role.upper()
        normalized_format = source_format.upper()

        existing = db.scalar(
            select(CatalogSourceFile).where(
                CatalogSourceFile.catalog_version_id == catalog_version_id,
                CatalogSourceFile.role == normalized_role,
            )
        )

        digest = sha256(content).hexdigest()

        if existing is None:
            existing = CatalogSourceFile(
                store_id=store_id,
                catalog_version_id=catalog_version_id,
                role=normalized_role,
                source_format=normalized_format,
                original_name=original_name,
                content_type=content_type,
                sha256=digest,
                content=content,
            )
            db.add(existing)
        else:
            existing.source_format = normalized_format
            existing.original_name = original_name
            existing.content_type = content_type
            existing.sha256 = digest
            existing.content = content

        db.flush()
        return existing

    def activate(
        self,
        db: Session,
        *,
        version: CatalogVersion,
        products_count: int,
        modifiers_count: int,
        relations_count: int,
    ) -> None:
        previous_versions = db.scalars(
            select(CatalogVersion).where(
                CatalogVersion.store_id == version.store_id,
                CatalogVersion.active.is_(True),
                CatalogVersion.id != version.id,
            )
        ).all()

        for previous in previous_versions:
            previous.active = False
            if previous.status == "ACTIVE":
                previous.status = "ARCHIVED"

        version.products_count = products_count
        version.modifiers_count = modifiers_count
        version.relations_count = relations_count
        version.status = "ACTIVE"
        version.active = True
        version.activated_at = datetime.now(timezone.utc)

        db.flush()

    def mark_failed(
        self,
        version: CatalogVersion,
        message: str,
    ) -> None:
        version.status = "FAILED"
        version.active = False
        version.notes = message[:2000]

    @staticmethod
    def _next_version_code(
        db: Session,
        store_id: UUID,
    ) -> str:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"CAT-{date_part}-"

        existing_codes = db.scalars(
            select(CatalogVersion.version_code).where(
                CatalogVersion.store_id == store_id,
                CatalogVersion.version_code.like(f"{prefix}%"),
            )
        ).all()

        sequence = 1

        for code in existing_codes:
            try:
                number = int(code.rsplit("-", 1)[1])
            except (ValueError, IndexError):
                continue
            sequence = max(sequence, number + 1)

        return f"{prefix}{sequence:03d}"
