from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.cart import Cart
from app.models.catalog import (
    Company,
    Modifier,
    Product,
    Store,
)
from app.models.customer import Customer
from app.models.order import (
    Order,
    OrderItem,
    OrderItemModifier,
)
from app.services.platform_analytics import (
    PlatformAnalyticsService,
)


def test_platform_analytics_aggregates_without_tenant_identity():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
    )
    Base.metadata.create_all(engine)
    db = Session(engine)

    now = datetime.now(timezone.utc)

    company_a = Company(
        name="Empresa Analytics A",
        active=True,
    )
    company_b = Company(
        name="Empresa Analytics B",
        active=True,
    )
    company_inactive = Company(
        name="Empresa Inativa",
        active=False,
    )

    db.add_all([
        company_a,
        company_b,
        company_inactive,
    ])
    db.flush()

    store_a = Store(
        company_id=company_a.id,
        name="Loja A",
        slug=f"global-a-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
        active=True,
    )

    store_b = Store(
        company_id=company_b.id,
        name="Loja B",
        slug=f"global-b-{uuid4()}",
        city="São Paulo",
        state="SP",
        timezone="America/Sao_Paulo",
        active=True,
    )

    store_inactive = Store(
        company_id=company_inactive.id,
        name="Loja Inativa",
        slug=f"global-inactive-{uuid4()}",
        city="Manaus",
        state="AM",
        timezone="America/Manaus",
        active=False,
    )

    db.add_all([
        store_a,
        store_b,
        store_inactive,
    ])
    db.flush()

    customer_a = Customer(
        store_id=store_a.id,
        name="Cliente Secreto A",
        phone="5597985000001",
    )

    customer_b = Customer(
        store_id=store_b.id,
        name="Cliente Secreto B",
        phone="5511985000002",
    )

    db.add_all([
        customer_a,
        customer_b,
    ])
    db.flush()

    burger_a = Product(
        store_id=store_a.id,
        external_code="BURGER-A",
        name="Hamburguer",
        price=Decimal("20.00"),
    )

    burger_b = Product(
        store_id=store_b.id,
        external_code="BURGER-B",
        name="Hamburguer",
        price=Decimal("20.00"),
    )

    pizza_b = Product(
        store_id=store_b.id,
        external_code="PIZZA-B",
        name="Pizza",
        price=Decimal("15.00"),
    )

    cheese_a = Modifier(
        store_id=store_a.id,
        external_code="CHEESE-A",
        name="Queijo Extra",
        price=Decimal("3.00"),
    )

    cheese_b = Modifier(
        store_id=store_b.id,
        external_code="CHEESE-B",
        name="Queijo Extra",
        price=Decimal("3.00"),
    )

    db.add_all([
        burger_a,
        burger_b,
        pizza_b,
        cheese_a,
        cheese_b,
    ])
    db.flush()

    valid_a_at = now - timedelta(hours=1)
    valid_b_at = now - timedelta(hours=2)
    valid_b2_at = now - timedelta(hours=3)
    cancelled_at = now - timedelta(minutes=30)

    def add_order(
        *,
        store,
        customer,
        product,
        display_id,
        status,
        service_mode,
        payment_method,
        quantity,
        total,
        created_at,
        modifier=None,
        modifier_quantity=0,
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
            created_at=created_at,
            updated_at=created_at,
        )

        db.add(order)
        db.flush()

        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_external_code=product.external_code,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
            total_price=(
                product.price * quantity
            ),
        )

        db.add(item)
        db.flush()

        if modifier is not None and modifier_quantity:
            db.add(
                OrderItemModifier(
                    order_item_id=item.id,
                    modifier_id=modifier.id,
                    modifier_external_code=(
                        modifier.external_code
                    ),
                    modifier_name=modifier.name,
                    quantity=modifier_quantity,
                    unit_price=modifier.price,
                    total_price=(
                        modifier.price
                        * modifier_quantity
                    ),
                )
            )

    add_order(
        store=store_a,
        customer=customer_a,
        product=burger_a,
        display_id="A-001",
        status="CONCLUDED",
        service_mode="DELIVERY",
        payment_method="PIX",
        quantity=2,
        total=Decimal("46.00"),
        created_at=valid_a_at,
        modifier=cheese_a,
        modifier_quantity=2,
    )

    add_order(
        store=store_b,
        customer=customer_b,
        product=burger_b,
        display_id="B-001",
        status="CONCLUDED",
        service_mode="TAKEOUT",
        payment_method="CARD",
        quantity=1,
        total=Decimal("23.00"),
        created_at=valid_b_at,
        modifier=cheese_b,
        modifier_quantity=1,
    )

    add_order(
        store=store_b,
        customer=customer_b,
        product=pizza_b,
        display_id="B-002",
        status="CONCLUDED",
        service_mode="DELIVERY",
        payment_method="PIX",
        quantity=1,
        total=Decimal("15.00"),
        created_at=valid_b2_at,
    )

    add_order(
        store=store_a,
        customer=customer_a,
        product=burger_a,
        display_id="A-CANCEL",
        status="CANCELLED",
        service_mode="DELIVERY",
        payment_method="PIX",
        quantity=10,
        total=Decimal("100.00"),
        created_at=cancelled_at,
        modifier=cheese_a,
        modifier_quantity=10,
    )

    db.commit()

    result = PlatformAnalyticsService().overview(
        db,
        hours=24,
    )

    summary = result["summary"]

    assert result["scope"] == "platform"

    assert summary["companies_total"] == 3
    assert summary["companies_active"] == 2
    assert summary["companies_with_orders"] == 2

    assert summary["stores_total"] == 3
    assert summary["stores_active"] == 2
    assert summary["stores_with_orders"] == 2

    assert summary["orders_total"] == 4
    assert summary["orders_valid"] == 3
    assert summary["orders_cancelled"] == 1

    assert summary["revenue"] == 84.0
    assert summary["average_ticket"] == 28.0

    modes = {
        item["service_mode"]: item
        for item in result["service_modes"]
    }

    assert modes["DELIVERY"]["orders"] == 2
    assert modes["DELIVERY"]["revenue"] == 61.0

    assert modes["TAKEOUT"]["orders"] == 1
    assert modes["TAKEOUT"]["revenue"] == 23.0

    payments = {
        item["payment_method"]: item
        for item in result["payment_methods"]
    }

    assert payments["PIX"]["orders"] == 2
    assert payments["PIX"]["revenue"] == 61.0

    assert payments["CARD"]["orders"] == 1
    assert payments["CARD"]["revenue"] == 23.0

    states = {
        item["state"]: item
        for item in result["states"]
    }

    assert states["AM"]["stores"] == 1
    assert states["AM"]["orders"] == 1
    assert states["AM"]["revenue"] == 46.0

    assert states["SP"]["stores"] == 1
    assert states["SP"]["orders"] == 2
    assert states["SP"]["revenue"] == 38.0

    cities = {
        (item["state"], item["city"]): item
        for item in result["cities"]
    }

    assert cities[("AM", "Coari")]["orders"] == 1
    assert cities[("AM", "Coari")]["revenue"] == 46.0

    assert cities[("SP", "São Paulo")]["orders"] == 2
    assert cities[("SP", "São Paulo")]["revenue"] == 38.0

    products = {
        item["name"]: item
        for item in result["top_products"]
    }

    assert products["Hamburguer"]["stores"] == 2
    assert products["Hamburguer"]["quantity"] == 3
    assert products["Hamburguer"]["revenue"] == 60.0

    assert products["Pizza"]["stores"] == 1
    assert products["Pizza"]["quantity"] == 1
    assert products["Pizza"]["revenue"] == 15.0

    modifiers = {
        item["name"]: item
        for item in result["top_modifiers"]
    }

    assert modifiers["Queijo Extra"]["stores"] == 2
    assert modifiers["Queijo Extra"]["quantity"] == 3
    assert modifiers["Queijo Extra"]["revenue"] == 9.0

    expected_hours = {}

    timed_orders = (
        (
            valid_a_at,
            ZoneInfo("America/Manaus"),
        ),
        (
            valid_b_at,
            ZoneInfo("America/Sao_Paulo"),
        ),
        (
            valid_b2_at,
            ZoneInfo("America/Sao_Paulo"),
        ),
    )

    for order_at, local_zone in timed_orders:
        local_hour = order_at.astimezone(
            local_zone
        ).hour

        expected_hours[local_hour] = (
            expected_hours.get(
                local_hour,
                0,
            )
            + 1
        )

    actual_hours = {
        item["hour"]: item["orders"]
        for item in result["orders_by_hour"]
        if item["orders"]
    }

    assert actual_hours == expected_hours

    expected_weekdays = {}

    for order_at, local_zone in timed_orders:
        weekday = order_at.astimezone(
            local_zone
        ).weekday()

        expected_weekdays[weekday] = (
            expected_weekdays.get(
                weekday,
                0,
            )
            + 1
        )

    actual_weekdays = {
        item["weekday"]: item["orders"]
        for item in result["orders_by_weekday"]
        if item["orders"]
    }

    assert actual_weekdays == expected_weekdays

    serialized = str(result)

    assert "Cliente Secreto A" not in serialized
    assert "Cliente Secreto B" not in serialized
    assert "5597985000001" not in serialized
    assert "5511985000002" not in serialized
    assert "Loja A" not in serialized
    assert "Loja B" not in serialized
    assert "Empresa Analytics A" not in serialized
    assert "Empresa Analytics B" not in serialized
