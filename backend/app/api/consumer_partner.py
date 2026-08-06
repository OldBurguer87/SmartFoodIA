from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.consumer import (
    ConsumerEventRead,
    ConsumerOrderEventRequest,
    ConsumerPollingResponse,
    ConsumerStatusRequest,
    ConsumerStatusResponse,
)
from app.services.consumer_partner import (
    ConsumerAuthenticationError,
    ConsumerNotFoundError,
    ConsumerPartnerService,
    ConsumerValidationError,
)

router = APIRouter(
    prefix="/api/v1/integrations/consumer/{store_slug}",
    tags=["consumer-partner"],
)
service = ConsumerPartnerService()


def authenticate(
    db: Session,
    store_slug: str,
    authorization: str | None,
):
    try:
        return service.authenticate(
            db,
            store_slug=store_slug,
            authorization=authorization,
        )
    except ConsumerAuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@router.get("/events", response_model=ConsumerPollingResponse)
def polling(
    store_slug: str,
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ConsumerPollingResponse:
    store, _ = authenticate(db, store_slug, authorization)
    return service.polling(db, store=store, limit=limit)


@router.get("/orders/{order_id}")
def order_details(
    store_slug: str,
    order_id: UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    store, integration = authenticate(db, store_slug, authorization)
    try:
        return service.order_details(
            db,
            store=store,
            integration=integration,
            order_id=order_id,
        )
    except ConsumerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/orders/{order_id}/events",
    response_model=ConsumerEventRead,
)
def receive_order_event(
    store_slug: str,
    order_id: UUID,
    payload: ConsumerOrderEventRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ConsumerEventRead:
    store, _ = authenticate(db, store_slug, authorization)
    if payload.OrderId != order_id:
        raise HTTPException(
            status_code=422,
            detail="OrderId do corpo difere do caminho.",
        )
    try:
        return service.receive_order_event(
            db,
            store=store,
            payload=payload,
        )
    except ConsumerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/orders/{order_id}/status",
    response_model=ConsumerStatusResponse,
)
def update_order_status(
    store_slug: str,
    order_id: UUID,
    payload: ConsumerStatusRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ConsumerStatusResponse:
    store, _ = authenticate(db, store_slug, authorization)
    if payload.orderId != order_id:
        raise HTTPException(
            status_code=422,
            detail="orderId do corpo difere do caminho.",
        )
    try:
        return service.update_status(db, store=store, payload=payload)
    except ConsumerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConsumerValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
