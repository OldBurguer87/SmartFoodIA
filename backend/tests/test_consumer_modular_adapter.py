from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from tests_support import configure_store_open
from app.integrations.consumer.adapter import (
    ConsumerPartnerAdapter,
    IntegrationOrderNotFound,
)
from app.integrations.consumer.mapper import ConsumerContractError
from app.models.catalog import Company, Product, Store
from app.models.integration import StoreIntegration
from app.models.payment import PaymentReceipt
from app.schemas.cart import CartItemAdd
from app.schemas.customer import AddressCreate, CustomerCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.customer import CustomerService


def setup(
    code="235",
    *,
    payment_method="PIX",
    receipt_status="AUTO_CONFIRMED",
    service_mode="DELIVERY",
):
    db = Session(create_engine("sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(db.get_bind())

    company = Company(name="Old")
    db.add(company)
    db.flush()

    store = Store(
        company_id=company.id,
        name="Old",
        slug=f"old-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.flush()
    configure_store_open(db, store)

    integration = StoreIntegration(
        store_id=store.id,
        provider="CONSUMER",
        token_hash="x" * 64,
        merchant_external_id="m1",
        merchant_name="Old",
        active=True,
    )
    db.add(integration)

    product = Product(
        store_id=store.id,
        external_code=code,
        name="Monster",
        price=Decimal("60"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add(product)
    db.commit()

    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente",
            phone="97999999999",
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
        service_mode=service_mode,
    )

    CartService().add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(
            product_external_code=code,
            quantity=1,
        ),
    )

    checkout_kwargs = {
        "payment_method": payment_method,
    }

    if service_mode == "DELIVERY":
        checkout_kwargs["address_id"] = address.id
        checkout_kwargs["delivery_fee"] = Decimal("5")

    order = CheckoutService().checkout(
        db,
        cart_id=cart.id,
        payload=CheckoutRequest(**checkout_kwargs),
    )

    if payment_method == "PIX" and receipt_status is not None:
        db.add(
            PaymentReceipt(
                store_id=store.id,
                order_id=order.id,
                external_media_id=f"consumer-test-{uuid4()}",
                media_type="IMAGE",
                file_sha256=uuid4().hex * 2,
                status=receipt_status,
            )
        )
        db.commit()

    return db, store, integration, order


def test_core_marks_order_ready_for_any_integration():
    db, store, _, order = setup()

    assert order.status == "READY_FOR_INTEGRATION"

    events = ConsumerPartnerAdapter().poll(
        db,
        store_id=store.id,
    )

    assert events[0].code == "PLC"


def test_adapter_maps_consumer_contract():
    db, store, integration, order = setup()

    payload = ConsumerPartnerAdapter().serialize_order(
        db,
        store_id=store.id,
        order_id=order.id,
        integration=integration,
    )

    assert payload["item"]["salesChannel"] == "PARTNER"
    assert payload["item"]["items"][0]["externalCode"] == "235"
    assert payload["item"]["total"]["orderAmount"] == 65.0


def test_mapper_rejects_missing_pdv_code():
    db, store, integration, order = setup()

    persisted = ConsumerPartnerAdapter().orders.get(
        db,
        order.id,
    )
    persisted.items[0].product_external_code = ""
    db.commit()

    with pytest.raises(ConsumerContractError):
        ConsumerPartnerAdapter().serialize_order(
            db,
            store_id=store.id,
            order_id=order.id,
            integration=integration,
        )


def test_status_is_idempotent():
    db, store, _, order = setup()
    adapter = ConsumerPartnerAdapter()

    assert adapter.apply_external_status(
        db,
        store_id=store.id,
        order_id=order.id,
        status="CONFIRMED",
    )[1] is True

    assert adapter.apply_external_status(
        db,
        store_id=store.id,
        order_id=order.id,
        status="CONFIRMED",
    )[1] is False


def test_pix_without_confirmation_is_hidden_from_consumer():
    db, store, integration, order = setup(
        receipt_status=None,
    )
    adapter = ConsumerPartnerAdapter()

    assert adapter.poll(
        db,
        store_id=store.id,
    ) == []

    with pytest.raises(
        IntegrationOrderNotFound,
        match="PIX ainda não confirmado",
    ):
        adapter.serialize_order(
            db,
            store_id=store.id,
            order_id=order.id,
            integration=integration,
        )


@pytest.mark.parametrize(
    "receipt_status",
    [
        "NEEDS_REVIEW",
        "HUMAN_REJECTED",
    ],
)
def test_unapproved_pix_receipt_does_not_release_order(
    receipt_status,
):
    db, store, integration, order = setup(
        receipt_status=receipt_status,
    )
    adapter = ConsumerPartnerAdapter()

    assert adapter.poll(
        db,
        store_id=store.id,
    ) == []

    with pytest.raises(IntegrationOrderNotFound):
        adapter.serialize_order(
            db,
            store_id=store.id,
            order_id=order.id,
            integration=integration,
        )


def test_human_confirmed_pix_releases_order():
    db, store, integration, order = setup(
        receipt_status="HUMAN_CONFIRMED",
    )
    adapter = ConsumerPartnerAdapter()

    events = adapter.poll(
        db,
        store_id=store.id,
    )

    assert len(events) == 1
    assert events[0].order_id == order.id

    payload = adapter.serialize_order(
        db,
        store_id=store.id,
        order_id=order.id,
        integration=integration,
    )

    assert payload["item"]["payments"]["methods"][0]["method"] == "PIX"


def test_non_pix_payment_does_not_require_receipt():
    db, store, integration, order = setup(
        payment_method="CASH",
        receipt_status=None,
    )
    adapter = ConsumerPartnerAdapter()

    events = adapter.poll(
        db,
        store_id=store.id,
    )

    assert len(events) == 1
    assert events[0].order_id == order.id

    payload = adapter.serialize_order(
        db,
        store_id=store.id,
        order_id=order.id,
        integration=integration,
    )

    assert payload["item"]["payments"]["methods"][0]["method"] == "CASH"


def test_takeout_pix_without_confirmation_is_hidden():
    db, store, integration, order = setup(
        service_mode="TAKEOUT",
        receipt_status=None,
    )
    adapter = ConsumerPartnerAdapter()

    assert adapter.poll(
        db,
        store_id=store.id,
    ) == []

    with pytest.raises(IntegrationOrderNotFound):
        adapter.serialize_order(
            db,
            store_id=store.id,
            order_id=order.id,
            integration=integration,
        )

def test_confirmed_pix_is_sent_to_consumer_as_prepaid():
    db, store, integration, order = setup(
        payment_method="PIX",
        receipt_status="AUTO_CONFIRMED",
    )

    payload = ConsumerPartnerAdapter().serialize_order(
        db,
        store_id=store.id,
        order_id=order.id,
        integration=integration,
    )

    payments = payload["item"]["payments"]
    method = payments["methods"][0]

    assert method["method"] == "PIX"
    assert method["type"] == "PREPAID"
    assert method["prepaid"] is True
    assert payments["pending"] == 0.0
    assert payments["prepaid"] == float(order.total)
