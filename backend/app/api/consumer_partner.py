from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.consumer import (
    ConsumerDiagnosticsResponse,
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


@router.get(
    "/diagnostics",
    response_model=ConsumerDiagnosticsResponse,
)
def diagnostics(
    store_slug: str,
    base_url: str = Query(
        ...,
        min_length=8,
        description="URL pública HTTPS sem barra final.",
    ),
    authorization: str | None = Header(default=None),
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> ConsumerDiagnosticsResponse:
    store, integration = authenticate(db, store_slug, authorization or x_apikey)
    return service.diagnostics(
        db,
        store=store,
        integration=integration,
        base_url=base_url,
    )


@router.get("/events", response_model=ConsumerPollingResponse)
def polling(
    store_slug: str,
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str | None = Header(default=None),
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> ConsumerPollingResponse:
    store, _ = authenticate(db, store_slug, authorization or x_apikey)
    return service.polling(db, store=store, limit=limit)


@router.get("/orders/{order_id}")
def order_details(
    store_slug: str,
    order_id: UUID,
    authorization: str | None = Header(default=None),
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> dict:
    store, integration = authenticate(db, store_slug, authorization or x_apikey)
    try:
        details = service.order_details(
            db,
            store=store,
            integration=integration,
            order_id=order_id,
        )

        db.execute(
            text(
                """
                UPDATE order_events
                SET status = 'DELIVERED', updated_at = now()
                WHERE order_id = :order_id
                  AND code = 'PLC'
                  AND status = 'PENDING'
                """
            ),
            {"order_id": order_id},
        )
        db.commit()

        return details
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
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> ConsumerEventRead:
    store, _ = authenticate(db, store_slug, authorization or x_apikey)
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
    except ConsumerValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/orders/{order_id}/status",
    response_model=ConsumerStatusResponse,
)
def update_order_status(
    store_slug: str,
    order_id: UUID,
    payload: ConsumerStatusRequest,
    authorization: str | None = Header(default=None),
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> ConsumerStatusResponse:
    store, _ = authenticate(db, store_slug, authorization or x_apikey)
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


@router.post(
    "/orders/status",
    response_model=ConsumerStatusResponse,
)
async def update_order_status_without_path_id(
    store_slug: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> ConsumerStatusResponse:
    store, _ = authenticate(db, store_slug, authorization or x_apikey)

    body = await request.body()

    print("CONSUMER_STATUS_BODY=" + body.decode("utf-8", errors="replace"))

    try:
        import json
        data = json.loads(body)
        if "OrderId" in data:
            data["orderId"] = data.pop("OrderId")
        if "Status" in data:
            data["status"] = data.pop("Status")
        if "Justification" in data:
            data["justification"] = data.pop("Justification")
        if isinstance(data.get("status"), str):
            data["status"] = data["status"].upper()
        payload = ConsumerStatusRequest.model_validate(data)
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Payload de status inválido: {error}",
        ) from error

    try:
        return service.update_status(db, store=store, payload=payload)
    except ConsumerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConsumerValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/orders/details",
    response_model=ConsumerStatusResponse,
)
async def receive_order_details_without_path_id(
    store_slug: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_apikey: str | None = Header(default=None, alias="xapikey"),
    db: Session = Depends(get_db),
) -> ConsumerStatusResponse:
    store, _ = authenticate(db, store_slug, authorization or x_apikey)

    try:
        data = await request.json()
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Payload de detalhes inválido: {error}",
        ) from error

    order_id = data.get("Id") or data.get("id") or data.get("OrderId") or data.get("orderId")
    display_id = data.get("DisplayId") or data.get("displayId")

    if order_id:
        try:
            parsed_order_id = UUID(str(order_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise HTTPException(
                status_code=422,
                detail="Id do pedido inválido.",
            ) from error

        db.execute(
            text(
                """
                UPDATE order_events
                SET status = 'DELIVERED', updated_at = now()
                WHERE order_id = :order_id
                  AND status = 'PENDING'
                  AND (
                        (code = 'ODR' AND full_code = 'ORDER_DETAILS_REQUESTED')
                        OR code = 'PLC'
                  )
                """
            ),
            {"order_id": parsed_order_id},
        )
        db.commit()

    print(
        "CONSUMER_ORDER_DETAILS "
        f"order_id={order_id} display_id={display_id} "
        f"keys={sorted(data.keys())}"
    )

    return ConsumerStatusResponse(
        statusCode=0,
        reasonPhrase=f"{order_id or 'Pedido'} recebido com sucesso.",
    )
