from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.order import CheckoutRequest, OrderRead
from app.services.checkout import CheckoutService, CheckoutValidationError

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])
service = CheckoutService()


@router.post("/checkout/{cart_id}", response_model=OrderRead)
def checkout_cart(
    cart_id: UUID,
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
) -> OrderRead:
    try:
        return service.checkout(db, cart_id=cart_id, payload=payload)
    except CheckoutValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
) -> OrderRead:
    try:
        return service.get(db, order_id)
    except CheckoutValidationError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
