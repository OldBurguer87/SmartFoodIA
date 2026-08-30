from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    require_store_access,
    require_store_write_access,
)
from app.database.session import get_db
from app.models.conversation import HumanTicket
from app.models.customer import Customer
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.schemas.conversation import (
    ConversationCreate,
    ConversationTakeoverRequest,
)
from app.services.auth import StoreAccess
from app.services.conversation import (
    ConversationService,
    ConversationStateError,
)


router = APIRouter(
    prefix="/api/v1/operations/stores",
    tags=["customer-operations"],
)


def address_to_dict(address) -> dict:
    return {
        "id": str(address.id),
        "label": address.label,
        "street": address.street,
        "number": address.number,
        "neighborhood": address.neighborhood,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "complement": address.complement,
        "reference": address.reference,
        "is_default": address.is_default,
        "active": address.active,
    }


def customer_to_dict(customer: Customer) -> dict:
    return {
        "id": str(customer.id),
        "store_id": str(customer.store_id),
        "name": customer.name,
        "phone": customer.phone,
        "active": customer.active,
        "addresses_count": sum(
            1
            for address in customer.addresses
            if address.active
        ),
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
    }


@router.get("/{store_id}/customers")
def list_customers(
    store_id: UUID,
    search: str | None = Query(
        default=None,
        max_length=160,
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(require_store_access),
) -> dict:
    filters = [
        Customer.store_id == store_id,
        Customer.active.is_(True),
    ]

    if search:
        term = f"%{search.strip()}%"

        filters.append(
            or_(
                Customer.name.ilike(term),
                Customer.phone.ilike(term),
            )
        )

    total = db.scalar(
        select(func.count())
        .select_from(Customer)
        .where(*filters)
    ) or 0

    customers = list(
        db.scalars(
            select(Customer)
            .where(*filters)
            .options(selectinload(Customer.addresses))
            .order_by(
                Customer.updated_at.desc(),
                Customer.name,
            )
            .offset(offset)
            .limit(limit)
        ).all()
    )

    return {
        "store_id": str(store_id),
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "customers": [
            customer_to_dict(customer)
            for customer in customers
        ],
    }


def _customer_whatsapp_recipient(phone: str) -> str:
    digits = "".join(
        character
        for character in str(phone)
        if character.isdigit()
    )

    if len(digits) in {10, 11}:
        digits = f"55{digits}"

    if (
        digits.startswith("55")
        and len(digits) == 12
        and digits[4] in "6789"
    ):
        digits = f"{digits[:4]}9{digits[4:]}"

    return digits


@router.post(
    "/{store_id}/customers/{customer_id}/conversation"
)
def open_customer_conversation(
    store_id: UUID,
    customer_id: UUID,
    payload: ConversationTakeoverRequest,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_store_write_access
    ),
) -> dict:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.store_id == store_id,
            Customer.active.is_(True),
        )
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado nesta loja.",
        )

    recipient = _customer_whatsapp_recipient(
        customer.phone
    )

    if not recipient:
        raise HTTPException(
            status_code=422,
            detail="Cliente sem telefone válido para WhatsApp.",
        )

    service = ConversationService()

    conversation = service.get_or_create(
        db,
        ConversationCreate(
            store_id=store_id,
            customer_id=customer.id,
            channel="WHATSAPP",
            external_conversation_id=recipient,
        ),
    )

    taken_over = False

    if conversation.status != "HUMAN":
        try:
            conversation = service.take_over(
                db,
                conversation_id=conversation.id,
                assigned_to=payload.assigned_to,
            )
            taken_over = True
        except ConversationStateError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            ) from error

    if taken_over:
        ticket = db.scalar(
            select(HumanTicket)
            .where(
                HumanTicket.conversation_id
                == conversation.id,
                HumanTicket.status.in_(
                    ["OPEN", "IN_PROGRESS"]
                ),
            )
            .order_by(
                HumanTicket.created_at.desc()
            )
            .limit(1)
        )

        if ticket is not None:
            service.assign_ticket(
                db,
                ticket_id=ticket.id,
                assigned_to=payload.assigned_to,
            )

    return {
        "conversation_id": str(conversation.id),
        "customer_id": str(customer.id),
        "status": conversation.status,
        "external_conversation_id":
            conversation.external_conversation_id,
    }


@router.get("/{store_id}/customers/{customer_id}")
def get_customer(
    store_id: UUID,
    customer_id: UUID,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(require_store_access),
) -> dict:
    customer = db.scalar(
        select(Customer)
        .where(
            Customer.id == customer_id,
            Customer.store_id == store_id,
            Customer.active.is_(True),
        )
        .options(selectinload(Customer.addresses))
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado nesta loja.",
        )

    orders = list(
        db.scalars(
            select(Order)
            .where(
                Order.store_id == store_id,
                Order.customer_id == customer_id,
            )
            .order_by(Order.created_at.desc())
            .limit(50)
        ).all()
    )

    confirmed_pix_order_ids = set()
    pix_order_ids = [
        order.id
        for order in orders
        if order.payment_method == "PIX"
    ]

    if pix_order_ids:
        confirmed_pix_order_ids = set(
            db.scalars(
                select(PaymentReceipt.order_id).where(
                    PaymentReceipt.store_id == store_id,
                    PaymentReceipt.order_id.in_(pix_order_ids),
                    PaymentReceipt.status.in_(
                        ["AUTO_CONFIRMED", "HUMAN_CONFIRMED"]
                    ),
                )
            ).all()
        )


    return {
        **customer_to_dict(customer),
        "addresses": [
            address_to_dict(address)
            for address in customer.addresses
            if address.active
        ],
        "orders": [
            {
                "id": str(order.id),
                "display_id": order.display_id,
                "status": order.status,
                "service_mode": order.service_mode,
                "payment_method": order.payment_method,
                "pix_confirmed": (
                    order.payment_method == "PIX"
                    and order.id in confirmed_pix_order_ids
                ),
                "total": order.total,
                "scheduled_for": order.scheduled_for,
                "created_at": order.created_at,
            }
            for order in orders
        ],
    }
