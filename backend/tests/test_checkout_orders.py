from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from tests_support import configure_store_open
from app.models.catalog import Company, Product, Store
from app.models.customer import CustomerAddress
from app.models.order import OrderEvent
from app.schemas.cart import CartItemAdd
from app.schemas.customer import AddressCreate, CustomerCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService, CheckoutValidationError
from app.services.customer import CustomerService


def setup_order_context(service_mode: str = "DELIVERY"):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Old Burguer 87")
    db.add(company)
    db.flush()
    store = Store(
        company_id=company.id,
        name="Old Burguer 87",
        slug=f"old-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.flush()
    configure_store_open(db, store)
    product = Product(
        store_id=store.id,
        external_code="235",
        name="Old Monster",
        description="Hambúrguer",
        price=Decimal("60.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add(product)
    db.commit()

    customer_service = CustomerService()
    customer = customer_service.find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente Teste",
            phone="97999999999",
        ),
    )
    address = customer_service.add_address(
        db,
        customer_id=customer.id,
        payload=AddressCreate(
            street="Rua Teste",
            number="10",
            neighborhood="Centro",
        ),
    )

    cart_service = CartService()
    cart = cart_service.create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode=service_mode,
    )
    cart = cart_service.add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(product_external_code="235", quantity=2),
    )
    return db, cart, address


def test_checkout_creates_persistent_order_and_event() -> None:
    db, cart, address = setup_order_context()
    service = CheckoutService()

    order = service.checkout(
        db,
        cart_id=cart.id,
        payload=CheckoutRequest(
            address_id=address.id,
            payment_method="PIX",
            delivery_fee=Decimal("5.00"),
        ),
    )

    assert order.subtotal == Decimal("120.00")
    assert order.total == Decimal("125.00")
    assert order.status == "READY_FOR_INTEGRATION"
    assert order.address.street == "Rua Teste"
    event = db.scalar(select(OrderEvent).where(OrderEvent.order_id == order.id))
    assert event.code == "PLC"
    assert event.status == "PENDING"


def test_checkout_is_idempotent_by_cart() -> None:
    db, cart, address = setup_order_context()
    service = CheckoutService()
    payload = CheckoutRequest(
        address_id=address.id,
        payment_method="DEBIT",
    )

    first = service.checkout(db, cart_id=cart.id, payload=payload)
    second = service.checkout(db, cart_id=cart.id, payload=payload)

    assert first.id == second.id


def test_delivery_requires_address() -> None:
    db, cart, _ = setup_order_context()
    with pytest.raises(CheckoutValidationError, match="Endereço"):
        CheckoutService().checkout(
            db,
            cart_id=cart.id,
            payload=CheckoutRequest(payment_method="PIX"),
        )


def test_takeout_does_not_require_address() -> None:
    db, cart, _ = setup_order_context(service_mode="TAKEOUT")
    order = CheckoutService().checkout(
        db,
        cart_id=cart.id,
        payload=CheckoutRequest(payment_method="CREDIT"),
    )
    assert order.address is None
    assert order.service_mode == "TAKEOUT"


def test_cash_change_must_cover_total() -> None:
    db, cart, address = setup_order_context()
    with pytest.raises(CheckoutValidationError, match="troco"):
        CheckoutService().checkout(
            db,
            cart_id=cart.id,
            payload=CheckoutRequest(
                address_id=address.id,
                payment_method="CASH",
                change_for=Decimal("50.00"),
            ),
        )

def test_pix_checkout_request_is_normalized_to_prepaid():
    from app.schemas.order import CheckoutRequest

    request = CheckoutRequest(
        payment_method="PIX",
        payment_type="PENDING",
    )

    assert request.payment_type == "PREPAID"


def test_non_pix_checkout_request_is_pending():
    from app.schemas.order import CheckoutRequest

    request = CheckoutRequest(
        payment_method="CASH",
        payment_type="PREPAID",
    )

    assert request.payment_type == "PENDING"
