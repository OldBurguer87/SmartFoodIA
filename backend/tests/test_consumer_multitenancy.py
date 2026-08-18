from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.consumer_partner import router
from app.database.base import Base
from app.database.session import get_db
from app.integrations.consumer.auth import hash_token
from app.models.cart import Cart
from app.models.catalog import Company, Store
from app.models.customer import Customer
from app.models.integration import StoreIntegration
from app.models.order import Order, OrderEvent


TOKEN_A = "consumer-tenant-a-secret"
TOKEN_B = "consumer-tenant-b-secret"


def setup_environment():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    db = SessionLocal()

    company_a = Company(
        name="Consumer Empresa A",
    )
    company_b = Company(
        name="Consumer Empresa B",
    )

    db.add_all([
        company_a,
        company_b,
    ])
    db.flush()

    store_a = Store(
        company_id=company_a.id,
        name="Consumer Loja A",
        slug="consumer-loja-a",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )

    store_b = Store(
        company_id=company_b.id,
        name="Consumer Loja B",
        slug="consumer-loja-b",
        city="Manaus",
        state="AM",
        timezone="America/Manaus",
    )

    db.add_all([
        store_a,
        store_b,
    ])
    db.flush()

    db.add_all([
        StoreIntegration(
            store_id=store_a.id,
            provider="CONSUMER",
            token_hash=hash_token(TOKEN_A),
            merchant_external_id="merchant-a",
            merchant_name="Consumer Loja A",
            active=True,
        ),
        StoreIntegration(
            store_id=store_b.id,
            provider="CONSUMER",
            token_hash=hash_token(TOKEN_B),
            merchant_external_id="merchant-b",
            merchant_name="Consumer Loja B",
            active=True,
        ),
    ])

    customer_a = Customer(
        store_id=store_a.id,
        name="Cliente A",
        phone="5597985000101",
    )

    customer_b = Customer(
        store_id=store_b.id,
        name="Cliente B",
        phone="5597985000202",
    )

    db.add_all([
        customer_a,
        customer_b,
    ])
    db.flush()

    cart_a = Cart(
        store_id=store_a.id,
        customer_id=customer_a.id,
        status="CHECKED_OUT",
        service_mode="DELIVERY",
    )

    cart_b = Cart(
        store_id=store_b.id,
        customer_id=customer_b.id,
        status="CHECKED_OUT",
        service_mode="DELIVERY",
    )

    db.add_all([
        cart_a,
        cart_b,
    ])
    db.flush()

    order_a = Order(
        store_id=store_a.id,
        customer_id=customer_a.id,
        cart_id=cart_a.id,
        display_id="000001",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PENDING",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("20.00"),
        customer_name=customer_a.name,
        customer_phone=customer_a.phone,
    )

    order_b = Order(
        store_id=store_b.id,
        customer_id=customer_b.id,
        cart_id=cart_b.id,
        display_id="000001",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PENDING",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("30.00"),
        customer_name=customer_b.name,
        customer_phone=customer_b.phone,
    )

    db.add_all([
        order_a,
        order_b,
    ])
    db.flush()

    event_a = OrderEvent(
        order_id=order_a.id,
        code="ODR",
        full_code="ORDER_DETAILS_REQUESTED",
        status="PENDING",
    )

    event_b = OrderEvent(
        order_id=order_b.id,
        code="ODR",
        full_code="ORDER_DETAILS_REQUESTED",
        status="PENDING",
    )

    db.add_all([
        event_a,
        event_b,
    ])
    db.commit()

    return {
        "client": client,
        "db": db,
        "engine": engine,
        "store_a": store_a,
        "store_b": store_b,
        "order_a": order_a,
        "order_b": order_b,
        "event_a": event_a,
        "event_b": event_b,
    }


def headers_a():
    return {
        "Authorization": f"Bearer {TOKEN_A}",
    }


def test_details_callback_updates_own_store():
    env = setup_environment()

    response = env["client"].post(
        (
            "/api/v1/integrations/consumer/"
            f"{env['store_a'].slug}/orders/details"
        ),
        headers=headers_a(),
        json={
            "Id": str(env["order_a"].id),
        },
    )

    assert response.status_code == 200

    env["db"].expire_all()

    event = env["db"].get(
        OrderEvent,
        env["event_a"].id,
    )

    assert event.status == "DELIVERED"


def test_details_callback_cannot_change_other_store():
    env = setup_environment()

    response = env["client"].post(
        (
            "/api/v1/integrations/consumer/"
            f"{env['store_a'].slug}/orders/details"
        ),
        headers=headers_a(),
        json={
            "Id": str(env["order_b"].id),
        },
    )

    assert response.status_code == 200

    env["db"].expire_all()

    event = env["db"].get(
        OrderEvent,
        env["event_b"].id,
    )

    assert event.status == "PENDING"


def test_status_callback_cannot_change_other_store():
    env = setup_environment()

    response = env["client"].post(
        (
            "/api/v1/integrations/consumer/"
            f"{env['store_a'].slug}/orders/status"
        ),
        headers=headers_a(),
        json={
            "orderId": str(env["order_b"].id),
            "status": "CONFIRMED",
        },
    )

    assert response.status_code == 404

    env["db"].expire_all()

    order = env["db"].get(
        Order,
        env["order_b"].id,
    )

    assert order.status == "READY_FOR_INTEGRATION"


def test_event_callback_cannot_change_other_store():
    env = setup_environment()

    response = env["client"].post(
        (
            "/api/v1/integrations/consumer/"
            f"{env['store_a'].slug}/orders/"
            f"{env['order_b'].id}/events"
        ),
        headers=headers_a(),
        json={
            "OrderId": str(env["order_b"].id),
            "EventCode": "ODR",
            "EventFullCode": "ORDER_DETAILS_REQUESTED",
        },
    )

    assert response.status_code == 404

    env["db"].expire_all()

    event = env["db"].get(
        OrderEvent,
        env["event_b"].id,
    )

    assert event.status == "PENDING"


def test_order_details_cannot_read_other_store():
    env = setup_environment()

    response = env["client"].get(
        (
            "/api/v1/integrations/consumer/"
            f"{env['store_a'].slug}/orders/"
            f"{env['order_b'].id}"
        ),
        headers=headers_a(),
    )

    assert response.status_code == 404
