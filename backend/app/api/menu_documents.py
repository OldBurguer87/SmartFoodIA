from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_store_access, require_store_write_access
from app.database.session import get_db
from app.services.auth import StoreAccess
from app.models.catalog import Store
from app.models.catalog_version import CatalogVersion
from app.models.menu import StoreMenuDocument


router = APIRouter(
    prefix="/api/v1/operations/stores",
    tags=["menu-documents"],
)

public_router = APIRouter(
    prefix="/api/v1/public/menu",
    tags=["public-menu"],
)

MAX_PDF_SIZE = 25 * 1024 * 1024


def get_active_catalog(
    db: Session,
    store_id: UUID,
) -> CatalogVersion | None:
    return db.scalar(
        select(CatalogVersion)
        .where(
            CatalogVersion.store_id == store_id,
            CatalogVersion.active.is_(True),
        )
        .order_by(CatalogVersion.created_at.desc())
        .limit(1)
    )


def serialize_document(
    db: Session,
    store_id: UUID,
    document: StoreMenuDocument | None,
) -> dict:
    active = get_active_catalog(db, store_id)

    linked_version = None

    if document is not None and document.catalog_version_id is not None:
        linked_version = db.get(
            CatalogVersion,
            document.catalog_version_id,
        )

    synchronized = bool(
        document is not None
        and active is not None
        and document.catalog_version_id == active.id
    )

    return {
        "store_id": str(store_id),
        "exists": document is not None,
        "synchronized": synchronized,
        "active_version_code": (
            active.version_code
            if active is not None
            else None
        ),
        "document": (
            {
                "id": str(document.id),
                "original_name": document.original_name,
                "content_type": document.content_type,
                "catalog_version_id": (
                    str(document.catalog_version_id)
                    if document.catalog_version_id
                    else None
                ),
                "catalog_version_code": (
                    linked_version.version_code
                    if linked_version is not None
                    else None
                ),
                "public_path": (
                    f"/api/v1/public/menu/{document.public_token}"
                ),
                "updated_at": document.updated_at,
            }
            if document is not None
            else None
        ),
    }


@router.get("/{store_id}/menu-pdf")
def get_menu_pdf_status(
    store_id: UUID,
    _access: StoreAccess = Depends(require_store_access),
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)

    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    document = db.scalar(
        select(StoreMenuDocument).where(
            StoreMenuDocument.store_id == store_id
        )
    )

    return serialize_document(
        db,
        store_id,
        document,
    )


@router.post("/{store_id}/menu-pdf")
async def upload_menu_pdf(
    store_id: UUID,
    pdf_file: UploadFile = File(...),
    _access: StoreAccess = Depends(require_store_write_access),
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)

    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    active = get_active_catalog(db, store_id)

    if active is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Não existe uma versão ativa do catálogo "
                "para vincular ao PDF."
            ),
        )

    filename = pdf_file.filename or "cardapio.pdf"

    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=422,
            detail="O cardápio visual deve ser um arquivo PDF.",
        )

    content = await pdf_file.read()

    if not content:
        raise HTTPException(
            status_code=422,
            detail="O arquivo PDF está vazio.",
        )

    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="O PDF é maior que 25 MB.",
        )

    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=422,
            detail="O arquivo enviado não é um PDF válido.",
        )

    document = db.scalar(
        select(StoreMenuDocument).where(
            StoreMenuDocument.store_id == store_id
        )
    )

    if document is None:
        document = StoreMenuDocument(
            store_id=store_id,
            catalog_version_id=active.id,
            original_name=filename,
            content_type="application/pdf",
            public_token=secrets.token_urlsafe(32),
            content=content,
        )
        db.add(document)
    else:
        document.catalog_version_id = active.id
        document.original_name = filename
        document.content_type = "application/pdf"
        document.content = content

    db.commit()
    db.refresh(document)

    return serialize_document(
        db,
        store_id,
        document,
    )


@router.delete("/{store_id}/menu-pdf")
def delete_menu_pdf(
    store_id: UUID,
    _access: StoreAccess = Depends(require_store_write_access),
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)

    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    document = db.scalar(
        select(StoreMenuDocument).where(
            StoreMenuDocument.store_id == store_id
        )
    )

    if document is None:
        return {
            "ok": True,
            "deleted": False,
        }

    db.delete(document)
    db.commit()

    return {
        "ok": True,
        "deleted": True,
    }


@public_router.get("/{public_token}")
def public_menu_pdf(
    public_token: str,
    db: Session = Depends(get_db),
) -> Response:
    document = db.scalar(
        select(StoreMenuDocument).where(
            StoreMenuDocument.public_token == public_token
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Cardápio não encontrado.",
        )

    encoded_name = quote(document.original_name)

    return Response(
        content=document.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{encoded_name}"
            ),
            "Cache-Control": "no-store",
        },
    )
