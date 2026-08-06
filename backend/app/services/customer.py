from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerAddress
from app.repositories.customer import CustomerRepository
from app.schemas.customer import AddressCreate, CustomerCreate


class CustomerNotFoundError(LookupError):
    pass


class CustomerService:
    def __init__(self, repository: CustomerRepository | None = None) -> None:
        self.repository = repository or CustomerRepository()

    def find_or_create(self, db: Session, payload: CustomerCreate) -> Customer:
        existing = self.repository.get_by_phone(
            db,
            store_id=payload.store_id,
            phone=payload.phone,
        )
        if existing is not None:
            if existing.name != payload.name:
                existing.name = payload.name
                db.commit()
                db.refresh(existing)
            return existing
        return self.repository.create(
            db,
            store_id=payload.store_id,
            name=payload.name,
            phone=payload.phone,
        )

    def add_address(
        self,
        db: Session,
        *,
        customer_id: UUID,
        payload: AddressCreate,
    ) -> CustomerAddress:
        customer = self.repository.get(db, customer_id)
        if customer is None:
            raise CustomerNotFoundError(str(customer_id))

        address_data = payload.model_dump()
        if not customer.addresses:
            address_data["is_default"] = True

        return self.repository.add_address(
            db,
            customer=customer,
            payload=address_data,
        )
