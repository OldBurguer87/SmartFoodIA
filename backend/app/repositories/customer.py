from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer, CustomerAddress


class CustomerRepository:
    def get_by_phone(
        self,
        db: Session,
        *,
        store_id: UUID,
        phone: str,
    ) -> Customer | None:
        statement = (
            select(Customer)
            .where(
                Customer.store_id == store_id,
                Customer.phone == phone,
                Customer.active.is_(True),
            )
            .options(selectinload(Customer.addresses))
        )
        return db.scalar(statement)

    def get(self, db: Session, customer_id: UUID) -> Customer | None:
        statement = (
            select(Customer)
            .where(Customer.id == customer_id, Customer.active.is_(True))
            .options(selectinload(Customer.addresses))
        )
        return db.scalar(statement)

    def create(
        self,
        db: Session,
        *,
        store_id: UUID,
        name: str,
        phone: str,
    ) -> Customer:
        customer = Customer(store_id=store_id, name=name, phone=phone, active=True)
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer

    def add_address(
        self,
        db: Session,
        *,
        customer: Customer,
        payload: dict,
    ) -> CustomerAddress:
        if payload.get("is_default"):
            db.execute(
                update(CustomerAddress)
                .where(CustomerAddress.customer_id == customer.id)
                .values(is_default=False)
            )
        address = CustomerAddress(customer_id=customer.id, active=True, **payload)
        db.add(address)
        db.commit()
        db.refresh(address)
        return address
