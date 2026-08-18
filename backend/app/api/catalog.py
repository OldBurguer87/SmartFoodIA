from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.database.session import get_db
from app.repositories.catalog import ProductRepository
from app.schemas.catalog import ProductCreate, ProductRead
from app.services.auth import (
    AuthenticatedUser,
    resolve_store_access,
)
from app.services.catalog.dto import ProductDTO, ProductSearchResultDTO
from app.services.catalog.exceptions import ProductNotFoundError
from app.services.catalog.service import CatalogService

router = APIRouter(
    prefix="/api/v1/products",
    tags=["products"],
)

repository = ProductRepository()
service = CatalogService(repository)


def require_catalog_write_access(
    db: Session,
    authenticated: AuthenticatedUser,
    *,
    store_id: UUID,
) -> None:
    access = resolve_store_access(
        db,
        authenticated.user,
        store_id,
    )

    if access is None:
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a esta loja.",
        )

    if not access.can_write:
        raise HTTPException(
            status_code=403,
            detail="Seu usuário não pode alterar esta loja.",
        )


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    payload: ProductCreate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> ProductRead:
    require_catalog_write_access(
        db,
        authenticated,
        store_id=payload.store_id,
    )

    existing = repository.get_by_external_code(
        db,
        store_id=payload.store_id,
        external_code=payload.external_code,
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Já existe um produto com este código externo "
                "nesta loja."
            ),
        )

    return repository.create(
        db,
        payload,
    )


@router.get(
    "",
    response_model=list[ProductDTO],
)
def list_products(
    store_id: UUID,
    delivery: bool | None = None,
    takeout: bool | None = None,
    db: Session = Depends(get_db),
) -> list[ProductDTO]:
    return service.list_available_products(
        db,
        store_id=store_id,
        delivery=delivery,
        takeout=takeout,
    )


@router.get(
    "/search",
    response_model=list[ProductSearchResultDTO],
)
def search_products(
    store_id: UUID,
    q: str = Query(
        min_length=2,
        max_length=100,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=30,
    ),
    delivery: bool | None = None,
    takeout: bool | None = None,
    db: Session = Depends(get_db),
) -> list[ProductSearchResultDTO]:
    return service.search_products(
        db,
        store_id=store_id,
        query=q,
        limit=limit,
        delivery=delivery,
        takeout=takeout,
    )


@router.get(
    "/{external_code}",
    response_model=ProductDTO,
)
def get_product(
    external_code: str,
    store_id: UUID,
    db: Session = Depends(get_db),
) -> ProductDTO:
    try:
        return service.get_by_external_code(
            db,
            store_id=store_id,
            external_code=external_code,
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Produto não encontrado.",
        ) from error
