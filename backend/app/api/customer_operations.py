from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_store_access
from app.database.session import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.services.auth import StoreAccess


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
                "total": order.total,
                "scheduled_for": order.scheduled_for,
                "created_at": order.created_at,
            }
            for order in orders
        ],
    }
