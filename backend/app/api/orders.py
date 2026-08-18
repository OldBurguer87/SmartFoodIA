from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.database.session import get_db
from app.repositories.cart import CartRepository
from app.repositories.order import OrderRepository
from app.schemas.order import CheckoutRequest, OrderRead
from app.services.auth import (
    AuthenticatedUser,
    resolve_store_access,
)
from app.services.checkout import (
    CheckoutService,
    CheckoutValidationError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

service = CheckoutService()
cart_repository = CartRepository()
order_repository = OrderRepository()


def require_order_store_access(
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


@router.post(
    "/checkout/{cart_id}",
    response_model=OrderRead,
)
def checkout_cart(
    cart_id: UUID,
    payload: CheckoutRequest,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> OrderRead:
    cart = cart_repository.get(
        db,
        cart_id,
    )

    if cart is None:
        raise HTTPException(
            status_code=422,
            detail="Carrinho não encontrado.",
        )

    require_order_store_access(
        db,
        authenticated,
        store_id=cart.store_id,
        write=True,
    )

    try:
        return service.checkout(
            db,
            cart_id=cart_id,
            payload=payload,
        )
    except CheckoutValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error


@router.get(
    "/{order_id}",
    response_model=OrderRead,
)
def get_order(
    order_id: UUID,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> OrderRead:
    order = order_repository.get(
        db,
        order_id,
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado.",
        )

    require_order_store_access(
        db,
        authenticated,
        store_id=order.store_id,
        write=False,
    )

    try:
        return service.get(
            db,
            order_id,
        )
    except CheckoutValidationError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
