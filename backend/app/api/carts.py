from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.database.session import get_db
from app.schemas.cart import (
    CartCreate,
    CartItemAdd,
    CartItemUpdate,
    CartRead,
)
from app.services.auth import (
    AuthenticatedUser,
    resolve_store_access,
)
from app.services.cart import (
    CartNotFoundError,
    CartService,
    CartValidationError,
)

router = APIRouter(prefix="/api/v1/carts", tags=["carts"])
service = CartService()


def handle_cart_error(error: Exception) -> HTTPException:
    if isinstance(error, CartNotFoundError):
        return HTTPException(
            status_code=404,
            detail="Carrinho não encontrado.",
        )

    return HTTPException(
        status_code=422,
        detail=str(error),
    )


def require_cart_store_access(
    db: Session,
    authenticated: AuthenticatedUser,
    *,
    store_id: UUID,
    write: bool,
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

    if write and not access.can_write:
        raise HTTPException(
            status_code=403,
            detail="Seu usuário não pode alterar esta loja.",
        )


def get_authorized_cart(
    db: Session,
    authenticated: AuthenticatedUser,
    *,
    cart_id: UUID,
    write: bool,
) -> CartRead:
    try:
        cart = service.get(db, cart_id)
    except CartNotFoundError as error:
        raise handle_cart_error(error) from error

    require_cart_store_access(
        db,
        authenticated,
        store_id=cart.store_id,
        write=write,
    )

    return cart


@router.post(
    "",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
)
def create_or_get_cart(
    payload: CartCreate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CartRead:
    require_cart_store_access(
        db,
        authenticated,
        store_id=payload.store_id,
        write=True,
    )

    try:
        return service.create_or_get_open(
            db,
            store_id=payload.store_id,
            customer_id=payload.customer_id,
            service_mode=payload.service_mode,
        )
    except CartValidationError as error:
        raise handle_cart_error(error) from error


@router.get("/{cart_id}", response_model=CartRead)
def get_cart(
    cart_id: UUID,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CartRead:
    return get_authorized_cart(
        db,
        authenticated,
        cart_id=cart_id,
        write=False,
    )


@router.post("/{cart_id}/items", response_model=CartRead)
def add_cart_item(
    cart_id: UUID,
    payload: CartItemAdd,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CartRead:
    get_authorized_cart(
        db,
        authenticated,
        cart_id=cart_id,
        write=True,
    )

    try:
        return service.add_item(
            db,
            cart_id=cart_id,
            payload=payload,
        )
    except (
        CartNotFoundError,
        CartValidationError,
    ) as error:
        raise handle_cart_error(error) from error


@router.patch(
    "/{cart_id}/items/{item_id}",
    response_model=CartRead,
)
def update_cart_item(
    cart_id: UUID,
    item_id: UUID,
    payload: CartItemUpdate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CartRead:
    get_authorized_cart(
        db,
        authenticated,
        cart_id=cart_id,
        write=True,
    )

    try:
        return service.update_item(
            db,
            cart_id=cart_id,
            item_id=item_id,
            payload=payload,
        )
    except (
        CartNotFoundError,
        CartValidationError,
    ) as error:
        raise handle_cart_error(error) from error


@router.delete(
    "/{cart_id}/items/{item_id}",
    response_model=CartRead,
)
def remove_cart_item(
    cart_id: UUID,
    item_id: UUID,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CartRead:
    get_authorized_cart(
        db,
        authenticated,
        cart_id=cart_id,
        write=True,
    )

    try:
        return service.remove_item(
            db,
            cart_id=cart_id,
            item_id=item_id,
        )
    except (
        CartNotFoundError,
        CartValidationError,
    ) as error:
        raise handle_cart_error(error) from error


@router.delete(
    "/{cart_id}/items",
    response_model=CartRead,
)
def clear_cart(
    cart_id: UUID,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CartRead:
    get_authorized_cart(
        db,
        authenticated,
        cart_id=cart_id,
        write=True,
    )

    try:
        return service.clear(
            db,
            cart_id,
        )
    except (
        CartNotFoundError,
        CartValidationError,
    ) as error:
        raise handle_cart_error(error) from error
