from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.customer import (
    AddressCreate,
    AddressRead,
    CustomerCreate,
    CustomerRead,
)
from app.services.customer import CustomerNotFoundError, CustomerService

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])
service = CustomerService()


@router.post(
    "/find-or-create",
    response_model=CustomerRead,
    status_code=status.HTTP_200_OK,
)
def find_or_create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
) -> CustomerRead:
    return service.find_or_create(db, payload)


@router.post(
    "/{customer_id}/addresses",
    response_model=AddressRead,
    status_code=status.HTTP_201_CREATED,
)
def add_customer_address(
    customer_id: UUID,
    payload: AddressCreate,
    db: Session = Depends(get_db),
) -> AddressRead:
    try:
        return service.add_address(
            db,
            customer_id=customer_id,
            payload=payload,
        )
    except CustomerNotFoundError as error:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.") from error
