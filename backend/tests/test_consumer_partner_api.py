from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from tests_support import configure_store_open
from app.models.catalog import Company, Product, Store
from app.models.integration import StoreIntegration
from app.models.order import OrderEvent
from app.models.payment import PaymentReceipt
from app.schemas.cart import CartItemAdd
from app.schemas.consumer import (
    ConsumerOrderEventRequest,
    ConsumerStatusRequest,
)
from app.schemas.customer import AddressCreate, CustomerCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.consumer_partner import (
    ConsumerAuthenticationError,
    ConsumerPartnerService,
    hash_token,
)
from app.services.customer import CustomerService


TOKEN = "consumer-test-token-1234567890"


def setup_context():
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
    db.add(
        StoreIntegration(
            store_id=store.id,
            provider="CONSUMER",
            token_hash=hash_token(TOKEN),
            merchant_external_id="merchant-old-87",
            merchant_name="Old Burguer 87",
            active=True,
        )
    )
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
            name="Cliente",
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
    cart = CartService().create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="DELIVERY",
    )
    cart = CartService().add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(product_external_code="235", quantity=1),
    )
    order = CheckoutService().checkout(
        db,
        cart_id=cart.id,
        payload=CheckoutRequest(
            address_id=address.id,
            payment_method="PIX",
            delivery_fee=Decimal("5.00"),
        ),
    )
    db.add(
        PaymentReceipt(
            store_id=store.id,
            order_id=order.id,
            external_media_id=f"consumer-confirmed-{uuid4()}",
            media_type="IMAGE",
            file_sha256=uuid4().hex * 2,
            status="AUTO_CONFIRMED",
        )
    )
    db.commit()
    return db, store, order


def test_authentication_uses_per_store_hashed_token() -> None:
    db, store, _ = setup_context()
    service = ConsumerPartnerService()

    authenticated_store, integration = service.authenticate(
        db,
        store_slug=store.slug,
        authorization=f"Bearer {TOKEN}",
    )

    assert authenticated_store.id == store.id
    assert integration.token_hash != TOKEN

    with pytest.raises(ConsumerAuthenticationError):
        service.authenticate(
            db,
            store_slug=store.slug,
            authorization="Bearer wrong-token",
        )


def test_polling_returns_pending_placed_event() -> None:
    db, store, order = setup_context()
    service = ConsumerPartnerService()
    _, integration = service.authenticate(
        db,
        store_slug=store.slug,
        authorization=f"Bearer {TOKEN}",
    )
    response = service.polling(
        db,
        store=store,
        integration=integration,
    )

    assert len(response.items) == 1
    assert response.items[0].orderId == order.id
    assert response.items[0].code == "PLC"


def test_order_details_match_consumer_contract() -> None:
    db, store, order = setup_context()
    service = ConsumerPartnerService()
    _, integration = service.authenticate(
        db,
        store_slug=store.slug,
        authorization=f"Bearer {TOKEN}",
    )

    payload = service.order_details(
        db,
        store=store,
        integration=integration,
        order_id=order.id,
    )

    assert payload["statusCode"] == 0
    assert payload["item"]["orderType"] == "DELIVERY"
    assert payload["item"]["merchant"]["id"] == "merchant-old-87"
    assert payload["item"]["items"][0]["externalCode"] == "235"
    assert payload["item"]["total"]["orderAmount"] == 65.0
    assert payload["item"]["payments"]["methods"][0]["method"] == "PIX"


def test_order_details_requested_acknowledges_placed_event() -> None:
    db, store, order = setup_context()
    service = ConsumerPartnerService()

    response = service.receive_order_event(
        db,
        store=store,
        payload=ConsumerOrderEventRequest(
            OrderId=order.id,
            EventCode="ODR",
            EventFullCode="ORDER_DETAILS_REQUESTED",
        ),
    )

    assert response.code == "ODR"
    placed = db.scalar(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id,
            OrderEvent.code == "PLC",
        )
    )
    assert placed.status == "DELIVERED"


def test_status_update_changes_order_and_is_idempotent() -> None:
    db, store, order = setup_context()
    service = ConsumerPartnerService()
    request = ConsumerStatusRequest(
        orderId=order.id,
        status="CONCLUDED",
        justification="Pedido finalizado",
    )

    first = service.update_status(db, store=store, payload=request)
    second = service.update_status(db, store=store, payload=request)

    persisted = CheckoutService().get(db, order.id)
    assert persisted.status == "CONCLUDED"
    assert "alterado" in first.reasonPhrase
    assert "já estava" in second.reasonPhrase
