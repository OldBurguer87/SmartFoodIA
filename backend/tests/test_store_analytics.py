from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.cart import Cart
from app.models.catalog import Company, Product, Store
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.services.store_analytics import StoreAnalyticsService


def setup_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
    )
    Base.metadata.create_all(engine)
    db = Session(engine)

    company_a = Company(name="Empresa A")
    company_b = Company(name="Empresa B")
    db.add_all([company_a, company_b])
    db.flush()

    store_a = Store(
        company_id=company_a.id,
        name="Loja A",
        slug=f"loja-a-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    store_b = Store(
        company_id=company_b.id,
        name="Loja B",
        slug=f"loja-b-{uuid4()}",
        city="Manaus",
        state="AM",
        timezone="America/Manaus",
    )
    db.add_all([store_a, store_b])
    db.flush()

    customer_a1 = Customer(
        store_id=store_a.id,
        name="Cliente A1",
        phone="5597981111111",
    )
    customer_a2 = Customer(
        store_id=store_a.id,
        name="Cliente A2",
        phone="5597982222222",
    )
    customer_b = Customer(
        store_id=store_b.id,
        name="Cliente B",
        phone="5597983333333",
    )
    db.add_all([
        customer_a1,
        customer_a2,
        customer_b,
    ])
    db.flush()

    product_a = Product(
        store_id=store_a.id,
        external_code="BURGER-A",
        name="Burger A",
        price=Decimal("20.00"),
    )
    product_b = Product(
        store_id=store_b.id,
        external_code="BURGER-B",
        name="Burger B",
        price=Decimal("99.00"),
    )
    db.add_all([product_a, product_b])
    db.flush()

    def add_order(
        *,
        store,
        customer,
        product,
        display_id,
        status,
        service_mode,
        payment_method,
        total,
        quantity,
    ):
        cart = Cart(
            store_id=store.id,
            customer_id=customer.id,
            status="CHECKED_OUT",
            service_mode=service_mode,
        )
        db.add(cart)
        db.flush()

        order = Order(
            store_id=store.id,
            customer_id=customer.id,
            cart_id=cart.id,
            display_id=display_id,
            status=status,
            service_mode=service_mode,
            payment_method=payment_method,
            payment_type="PENDING",
            subtotal=total,
            delivery_fee=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=total,
            customer_name=customer.name,
            customer_phone=customer.phone,
        )
        db.add(order)
        db.flush()

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_external_code=product.external_code,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price,
                total_price=product.price * quantity,
            )
        )

    add_order(
        store=store_a,
        customer=customer_a1,
        product=product_a,
        display_id="A-001",
        status="CONCLUDED",
        service_mode="DELIVERY",
        payment_method="PIX",
        total=Decimal("40.00"),
        quantity=2,
    )

    add_order(
        store=store_a,
        customer=customer_a2,
        product=product_a,
        display_id="A-002",
        status="CONCLUDED",
        service_mode="TAKEOUT",
        payment_method="CARD",
        total=Decimal("20.00"),
        quantity=1,
    )

    add_order(
        store=store_a,
        customer=customer_a1,
        product=product_a,
        display_id="A-003",
        status="CANCELLED",
        service_mode="DELIVERY",
        payment_method="PIX",
        total=Decimal("100.00"),
        quantity=5,
    )

    add_order(
        store=store_b,
        customer=customer_b,
        product=product_b,
        display_id="B-001",
        status="CONCLUDED",
        service_mode="DELIVERY",
        payment_method="PIX",
        total=Decimal("999.00"),
        quantity=10,
    )

    db.commit()

    return db, store_a


def test_store_analytics_calculates_and_isolates_data():
    db, store = setup_db()

    result = StoreAnalyticsService().overview(
        db,
        store_id=store.id,
        hours=24,
    )

    assert result["store_id"] == str(store.id)

    summary = result["summary"]

    assert summary["orders_total"] == 3
    assert summary["orders_valid"] == 2
    assert summary["orders_cancelled"] == 1
    assert summary["revenue"] == 60.0
    assert summary["average_ticket"] == 30.0
    assert summary["unique_customers"] == 2

    modes = {
        item["service_mode"]: item
        for item in result["service_modes"]
    }

    assert modes["DELIVERY"]["orders"] == 1
    assert modes["DELIVERY"]["revenue"] == 40.0
    assert modes["TAKEOUT"]["orders"] == 1
    assert modes["TAKEOUT"]["revenue"] == 20.0

    payments = {
        item["payment_method"]: item
        for item in result["payment_methods"]
    }

    assert payments["PIX"]["orders"] == 1
    assert payments["PIX"]["revenue"] == 40.0
    assert payments["CARD"]["orders"] == 1
    assert payments["CARD"]["revenue"] == 20.0

    assert len(result["top_products"]) == 1

    product = result["top_products"][0]

    assert product["external_code"] == "BURGER-A"
    assert product["name"] == "Burger A"
    assert product["quantity"] == 3
    assert product["revenue"] == 60.0

    assert all(
        item["external_code"] != "BURGER-B"
        for item in result["top_products"]
    )
