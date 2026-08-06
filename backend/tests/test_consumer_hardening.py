from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.integrations.consumer.adapter import IntegrationStatusError
from app.models.catalog import Company, Product, Store
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.integration import StoreIntegration
from app.schemas.cart import CartItemAdd
from app.schemas.consumer import ConsumerOrderEventRequest
from app.schemas.customer import AddressCreate, CustomerCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.consumer_partner import ConsumerPartnerService
from app.services.customer import CustomerService


def setup_context(store_name: str = "Hamburgueria Teste"):
    db = Session(create_engine("sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(db.get_bind())
    company = Company(name=store_name)
    db.add(company)
    db.flush()
    store = Store(
        company_id=company.id,
        name=store_name,
        slug=f"store-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.flush()
    db.add(
        StoreIntegration(
            store_id=store.id,
            provider="CONSUMER",
            token_hash="x" * 64,
            merchant_external_id="merchant-1",
            merchant_name=store_name,
            active=True,
        )
    )
    db.add(
        ChannelAccount(
            store_id=store.id,
            provider="WHATSAPP_CLOUD",
            external_account_id="phone-1",
            verify_token_hash="hash",
            active=True,
        )
    )
    db.add(
        Product(
            store_id=store.id,
            external_code="235",
            name="Produto",
            price=Decimal("20"),
            active=True,
            available_for_delivery=True,
            available_for_takeout=True,
        )
    )
    db.commit()

    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente",
            phone="5597999999999",
        ),
    )
    address = CustomerService().add_address(
        db,
        customer_id=customer.id,
        payload=AddressCreate(
            street="Rua",
            number="1",
            neighborhood="Centro",
            city="Coari",
            state="AM",
        ),
    )
    cart = CartService().create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="DELIVERY",
    )
    CartService().add_item(
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
            delivery_fee=Decimal("5"),
        ),
    )
    return db, store, order


def test_order_event_schema_rejects_non_odr_code():
    with pytest.raises(ValidationError):
        ConsumerOrderEventRequest(
            OrderId=uuid4(),
            EventCode="PLC",
            EventFullCode="PLACED",
        )


def test_adapter_rejects_non_details_event_even_without_schema():
    db, store, order = setup_context()
    with pytest.raises(IntegrationStatusError):
        ConsumerPartnerService().adapter.acknowledge_details_request(
            db,
            store_id=store.id,
            order_id=order.id,
            code="PLC",
            full_code="PLACED",
        )


def test_status_notification_uses_current_store_name():
    db, store, order = setup_context("Loja Modular")

    class Payload:
        orderId = order.id
        status = "CONFIRMED"
        justification = None

    ConsumerPartnerService().update_status(
        db,
        store=store,
        payload=Payload(),
    )

    message = db.scalar(select(OutboundChannelMessage))
    assert message is not None
    assert "Loja Modular" in message.content
    assert "Old Burguer 87" not in message.content
