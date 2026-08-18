from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.database.session import get_db
from app.repositories.customer import CustomerRepository
from app.schemas.customer import (
    AddressCreate,
    AddressRead,
    CustomerCreate,
    CustomerRead,
)
from app.services.auth import (
    AuthenticatedUser,
    resolve_store_access,
)
from app.services.customer import (
    CustomerNotFoundError,
    CustomerService,
)

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["customers"],
)

service = CustomerService()
repository = CustomerRepository()


def require_customer_store_write_access(
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
    "/find-or-create",
    response_model=CustomerRead,
    status_code=status.HTTP_200_OK,
)
def find_or_create_customer(
    payload: CustomerCreate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> CustomerRead:
    require_customer_store_write_access(
        db,
        authenticated,
        store_id=payload.store_id,
    )

    return service.find_or_create(
        db,
        payload,
    )


@router.post(
    "/{customer_id}/addresses",
    response_model=AddressRead,
    status_code=status.HTTP_201_CREATED,
)
def add_customer_address(
    customer_id: UUID,
    payload: AddressCreate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> AddressRead:
    customer = repository.get(
        db,
        customer_id,
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado.",
        )

    require_customer_store_write_access(
        db,
        authenticated,
        store_id=customer.store_id,
    )

    try:
        return service.add_address(
            db,
            customer_id=customer_id,
            payload=payload,
        )
    except CustomerNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado.",
        ) from error
