from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.catalog import (
    Modifier,
    ModifierGroup,
    ModifierGroupItem,
    Product,
    Store,
)
from app.models.catalog_version import (
    CatalogSourceFile,
    CatalogVersion,
)
from app.services.catalog.importer import ConsumerCatalogImportService
from app.services.catalog.consumer_families import ConsumerFamilyImportService
from app.services.catalog.prodcon_importer import (
    MANAGED_GROUP_PREFIX,
    ConsumerProdconImportService,
)
from app.services.catalog_versioning import CatalogVersioningService


router = APIRouter(
    prefix="/api/v1/operations/stores",
    tags=["catalog-operations"],
)

versioning = CatalogVersioningService()
catalog_importer = ConsumerCatalogImportService()
family_importer = ConsumerFamilyImportService()
prodcon_importer = ConsumerProdconImportService()

MAX_FILE_SIZE = 25 * 1024 * 1024


async def read_upload(
    file: UploadFile,
    *,
    allowed_extensions: set[str],
) -> bytes:
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Formato inválido para {file.filename}. "
                f"Permitidos: {', '.join(sorted(allowed_extensions))}."
            ),
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=422,
            detail=f"O arquivo {file.filename} está vazio.",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Arquivo maior que 25 MB.",
        )

    return content


def validate_xlsx(content: bytes, file_name: str) -> None:
    try:
        workbook = load_workbook(
            BytesIO(content),
            read_only=True,
            data_only=True,
        )
        workbook.close()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Arquivo Excel inválido: {file_name}.",
        ) from exc


def active_counts(db: Session, store_id: UUID) -> tuple[int, int, int]:
    products_count = db.scalar(
        select(func.count())
        .select_from(Product)
        .where(
            Product.store_id == store_id,
            Product.active.is_(True),
        )
    ) or 0

    modifiers_count = db.scalar(
        select(func.count())
        .select_from(Modifier)
        .where(
            Modifier.store_id == store_id,
            Modifier.active.is_(True),
        )
    ) or 0

    relations_count = db.scalar(
        select(func.count())
        .select_from(ModifierGroupItem)
        .join(
            ModifierGroup,
            ModifierGroup.id == ModifierGroupItem.modifier_group_id,
        )
        .where(
            ModifierGroup.store_id == store_id,
            ModifierGroup.name.startswith(MANAGED_GROUP_PREFIX),
        )
    ) or 0

    return (
        int(products_count),
        int(modifiers_count),
        int(relations_count),
    )


@router.get("/{store_id}/catalog")
def get_catalog_status(
    store_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)

    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    versions = db.scalars(
        select(CatalogVersion)
        .where(CatalogVersion.store_id == store_id)
        .order_by(CatalogVersion.created_at.desc())
        .limit(10)
    ).all()

    active = next(
        (version for version in versions if version.active),
        None,
    )

    source_files = []

    if active is not None:
        files = db.scalars(
            select(CatalogSourceFile)
            .where(
                CatalogSourceFile.catalog_version_id == active.id
            )
            .order_by(CatalogSourceFile.role)
        ).all()

        source_files = [
            {
                "role": item.role,
                "format": item.source_format,
                "original_name": item.original_name,
                "sha256": item.sha256,
                "updated_at": item.updated_at,
            }
            for item in files
        ]

    return {
        "store_id": str(store_id),
        "store_name": store.name,
        "active_version": (
            {
                "id": str(active.id),
                "version_code": active.version_code,
                "provider": active.provider,
                "status": active.status,
                "products_count": active.products_count,
                "modifiers_count": active.modifiers_count,
                "relations_count": active.relations_count,
                "activated_at": active.activated_at,
                "source_files": source_files,
            }
            if active is not None
            else None
        ),
        "versions": [
            {
                "id": str(version.id),
                "version_code": version.version_code,
                "provider": version.provider,
                "status": version.status,
                "active": version.active,
                "products_count": version.products_count,
                "modifiers_count": version.modifiers_count,
                "relations_count": version.relations_count,
                "created_at": version.created_at,
                "activated_at": version.activated_at,
                "notes": version.notes,
            }
            for version in versions
        ],
    }


@router.post("/{store_id}/catalog/import/consumer")
async def import_consumer_catalog(
    store_id: UUID,
    main_file: UploadFile = File(...),
    complements_file: UploadFile | None = File(default=None),
    prodcon_file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)

    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    main_content = await read_upload(
        main_file,
        allowed_extensions={".xlsx"},
    )
    validate_xlsx(
        main_content,
        main_file.filename or "cardapio-principal.xlsx",
    )

    complements_content: bytes | None = None

    if complements_file is not None:
        complements_content = await read_upload(
            complements_file,
            allowed_extensions={".xlsx"},
        )
        validate_xlsx(
            complements_content,
            complements_file.filename or "complementos.xlsx",
        )

    prodcon_content = await read_upload(
        prodcon_file,
        allowed_extensions={".prodcon"},
    )

    config = versioning.get_or_create_config(
        db,
        store_id=store_id,
        provider="CONSUMER",
    )
    config.provider = "CONSUMER"
    config.products_source = "XLSX"
    config.complements_source = (
        "XLSX+PRODCON"
        if complements_content is not None
        else "PRODCON"
    )
    config.relations_source = "PRODCON"

    version = versioning.create_version(
        db,
        store_id=store_id,
        provider="CONSUMER",
    )

    version.status = "IMPORTING"

    versioning.save_source_file(
        db,
        store_id=store_id,
        catalog_version_id=version.id,
        role="MAIN",
        source_format="XLSX",
        original_name=main_file.filename or "cardapio.xlsx",
        content_type=(
            main_file.content_type
            or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        content=main_content,
    )

    if complements_content is not None:
        versioning.save_source_file(
            db,
            store_id=store_id,
            catalog_version_id=version.id,
            role="COMPLEMENTS",
            source_format="XLSX",
            original_name=(
                complements_file.filename
                if complements_file is not None
                else "complementos.xlsx"
            ),
            content_type=(
                complements_file.content_type
                if complements_file is not None
                and complements_file.content_type
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            content=complements_content,
        )

    versioning.save_source_file(
        db,
        store_id=store_id,
        catalog_version_id=version.id,
        role="PRODCON",
        source_format="PRODCON",
        original_name=prodcon_file.filename or "cardapio.prodcon",
        content_type=(
            prodcon_file.content_type
            or "application/octet-stream"
        ),
        content=prodcon_content,
    )

    # Salva a versão/importação antes de alterar o catálogo.
    # Assim, em caso de falha, conseguimos registrar FAILED.
    db.commit()
    version_id = version.id

    try:
        with tempfile.TemporaryDirectory(
            prefix="smartfoodia-catalog-"
        ) as temp_dir:
            main_path = Path(temp_dir) / "main.xlsx"
            main_path.write_bytes(main_content)

            main_report = catalog_importer.import_workbook(
                db,
                store_id=store_id,
                file_path=main_path,
                commit=False,
            )

            family_report = family_importer.import_workbook(
                db,
                store_id=store_id,
                file_path=main_path,
            )

            # No formato Consumer validado, as linhas Pxx sem preço
            # representam famílias/agrupadores. Qualquer outra linha
            # inválida deve impedir a ativação do catálogo.
            if main_report.conflicts_skipped:
                raise ValueError(
                    "Existem conflitos de Código PDV no Excel principal."
                )

            if main_report.invalid_rows != family_report.families_found:
                raise ValueError(
                    "O Excel possui linhas inválidas além dos "
                    "agrupadores Pxx esperados."
                )

            prodcon_path = Path(temp_dir) / "catalog.prodcon"
            prodcon_path.write_bytes(prodcon_content)

            prodcon_report = prodcon_importer.import_file(
                db,
                store_id=store_id,
                file_path=prodcon_path,
                commit=False,
            )

            products_count, modifiers_count, relations_count = (
                active_counts(db, store_id)
            )

            version = db.get(CatalogVersion, version_id)

            if version is None:
                raise RuntimeError(
                    "Versão do catálogo desapareceu durante a importação."
                )

            versioning.activate(
                db,
                version=version,
                products_count=products_count,
                modifiers_count=modifiers_count,
                relations_count=relations_count,
            )

            db.commit()

    except Exception as exc:
        db.rollback()

        failed_version = db.get(CatalogVersion, version_id)

        if failed_version is not None:
            versioning.mark_failed(
                failed_version,
                str(exc),
            )
            db.commit()

        raise HTTPException(
            status_code=422,
            detail=f"Falha ao importar catálogo: {exc}",
        ) from exc

    return {
        "ok": True,
        "store_id": str(store_id),
        "version_code": version.version_code,
        "status": version.status,
        "products_count": products_count,
        "modifiers_count": modifiers_count,
        "relations_count": relations_count,
        "main_import": {
            "rows_read": main_report.rows_read,
            "rows_valid": main_report.rows_valid,
            "products_created": main_report.products_created,
            "products_updated": main_report.products_updated,
            "products_deactivated": main_report.products_deactivated,
            "invalid_rows": main_report.invalid_rows,
            "conflicts_skipped": main_report.conflicts_skipped,
        },
        "complements_excel": {
            "provided": complements_content is not None,
            "stored": complements_content is not None,
            "imported": False,
            "note": (
                "Arquivo armazenado na versão; parser será ligado após "
                "validarmos o formato real exportado pelo Consumer."
                if complements_content is not None
                else "Nenhum Excel de complementos enviado."
            ),
        },
        "family_import": {
            "families_found": family_report.families_found,
            "families_created": family_report.families_created,
            "families_updated": family_report.families_updated,
            "families_deactivated": family_report.families_deactivated,
            "product_links": family_report.product_links,
            "child_products_missing": family_report.child_products_missing,
        },
        "prodcon_import": (
            {
                "consumer_version": prodcon_report.consumer_version,
                "modifiers_created": prodcon_report.modifiers_created,
                "modifiers_updated": prodcon_report.modifiers_updated,
                "products_with_complements": (
                    prodcon_report.products_with_complements
                ),
                "relations_created": (
                    prodcon_report.group_items_created
                ),
                "products_not_found": (
                    prodcon_report.products_not_found
                ),
            }
            if prodcon_report is not None
            else None
        ),
    }
