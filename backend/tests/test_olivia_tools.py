from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.tools.context import ToolContext
from app.ai.tools.registry import OliviaToolRegistry
from app.database.base import Base
from app.models.catalog import Company, Product, Store


def setup_registry():
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
    db.add(
        Product(
            store_id=store.id,
            external_code="235",
            name="Old Monster",
            description="Hambúrguer artesanal com bacon",
            price=Decimal("60.00"),
            active=True,
            available_for_delivery=True,
            available_for_takeout=True,
        )
    )
    db.commit()

    registry = OliviaToolRegistry(
        ToolContext(
            db=db,
            store_id=store.id,
            customer_phone="97999999999",
        )
    )
    return db, store, registry


def test_registry_exposes_openai_function_definitions() -> None:
    _, _, registry = setup_registry()
    definitions = registry.openai_definitions()

    names = {item["function"]["name"] for item in definitions}
    assert "search_catalog" in names
    assert "add_cart_item" in names
    assert "checkout_cart" in names
    assert "request_human_help" in names


def test_search_catalog_tool_returns_real_product() -> None:
    _, _, registry = setup_registry()

    result = registry.execute(
        "search_catalog",
        {"query": "monster", "service_mode": "DELIVERY"},
    )

    assert result.ok is True
    assert result.data["products"][0]["external_code"] == "235"
    assert result.data["products"][0]["price"] == 60.0


def test_customer_and_cart_tools_work_together() -> None:
    _, _, registry = setup_registry()

    customer_result = registry.execute(
        "find_or_create_customer",
        {"name": "Cliente", "phone": "(97) 99999-9999"},
    )
    customer_id = customer_result.data["id"]

    cart_result = registry.execute(
        "get_or_create_cart",
        {
            "customer_id": customer_id,
            "service_mode": "TAKEOUT",
        },
    )
    cart_id = cart_result.data["id"]

    add_result = registry.execute(
        "add_cart_item",
        {
            "cart_id": cart_id,
            "product_external_code": "235",
            "quantity": 2,
            "observations": "Sem cebola",
        },
    )

    assert add_result.ok is True
    assert add_result.data["subtotal"] == 120.0
    assert add_result.data["items"][0]["observations"] == "Sem cebola"


def test_checkout_tool_requires_explicit_confirmation() -> None:
    _, _, registry = setup_registry()
    customer = registry.execute(
        "find_or_create_customer",
        {"name": "Cliente", "phone": "97988887777"},
    )
    cart = registry.execute(
        "get_or_create_cart",
        {
            "customer_id": customer.data["id"],
            "service_mode": "TAKEOUT",
        },
    )
    registry.execute(
        "add_cart_item",
        {
            "cart_id": cart.data["id"],
            "product_external_code": "235",
        },
    )

    blocked = registry.execute(
        "checkout_cart",
        {
            "cart_id": cart.data["id"],
            "payment_method": "PIX",
            "customer_confirmed": False,
        },
    )
    assert blocked.ok is False
    assert "não confirmou" in blocked.error

    completed = registry.execute(
        "checkout_cart",
        {
            "cart_id": cart.data["id"],
            "payment_method": "PIX",
            "customer_confirmed": True,
        },
    )
    assert completed.ok is True
    assert completed.data["status"] == "READY_FOR_INTEGRATION"


def test_human_help_tool_returns_structured_escalation() -> None:
    _, store, registry = setup_registry()

    result = registry.execute(
        "request_human_help",
        {
            "reason": "Preço não confirmado",
            "customer_message": "Quanto custa o adicional especial?",
            "category": "PRICE",
        },
    )

    assert result.ok is True
    assert result.requires_human is True
    assert result.data["store_id"] == str(store.id)
    assert result.data["customer_phone"] == "97999999999"
