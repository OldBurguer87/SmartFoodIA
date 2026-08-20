from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.olivia_prompt import OLIVIA_INSTRUCTIONS
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import OliviaToolRegistry
from app.database.base import Base
from tests_support import configure_store_open
from app.models.catalog import Company, Product, Store
from app.models.conversation import AIEvent, Conversation, HumanTicket
from app.models.customer import CustomerAddress
from app.models.order import Order
from app.schemas.customer import CustomerCreate
from app.services.customer import CustomerService


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
    configure_store_open(db, store)
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


def test_add_customer_address_accepts_customer_from_same_store() -> None:
    _, _, registry = setup_registry()

    customer = registry.execute(
        "find_or_create_customer",
        {
            "name": "Cliente Local",
            "phone": "97981112222",
        },
    )

    result = registry.execute(
        "add_customer_address",
        {
            "customer_id": customer.data["id"],
            "street": "Rua Local",
            "number": "10",
            "neighborhood": "Centro",
            "reference": "Próximo à igreja",
        },
    )

    assert result.ok is True
    assert result.data["customer_id"] == customer.data["id"]


def test_add_customer_address_requires_reference() -> None:
    _, _, registry = setup_registry()

    customer = registry.execute(
        "find_or_create_customer",
        {
            "name": "Cliente Sem Referência",
            "phone": "97981113333",
        },
    )

    result = registry.execute(
        "add_customer_address",
        {
            "customer_id": customer.data["id"],
            "street": "Rua Sem Referência",
            "number": "20",
            "neighborhood": "Centro",
        },
    )

    assert result.ok is False
    assert "Ponto de referência é obrigatório" in result.error


def test_add_customer_address_accepts_explicit_no_reference() -> None:
    _, _, registry = setup_registry()

    customer = registry.execute(
        "find_or_create_customer",
        {
            "name": "Cliente Sem Ponto",
            "phone": "97981114444",
        },
    )

    result = registry.execute(
        "add_customer_address",
        {
            "customer_id": customer.data["id"],
            "street": "Rua Sem Ponto",
            "number": "30",
            "neighborhood": "Centro",
            "reference": "Sem referência",
        },
    )

    assert result.ok is True

    addresses = registry.execute(
        "list_customer_addresses",
        {
            "customer_id": customer.data["id"],
        },
    )

    assert addresses.ok is True
    assert addresses.data["addresses"][0]["reference"] == "Sem referência"


def test_add_customer_address_blocks_customer_from_another_store() -> None:
    db, _, registry = setup_registry()

    company_b = Company(name="Empresa B")
    db.add(company_b)
    db.flush()

    store_b = Store(
        company_id=company_b.id,
        name="Loja B",
        slug=f"loja-b-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store_b)
    db.flush()

    customer_b = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store_b.id,
            name="Cliente Empresa B",
            phone="97983334444",
        ),
    )

    result = registry.execute(
        "add_customer_address",
        {
            "customer_id": str(customer_b.id),
            "street": "Rua Empresa B",
            "number": "20",
            "neighborhood": "Centro",
            "reference": "Próximo ao mercado",
        },
    )

    assert result.ok is False
    assert result.error == "Cliente não encontrado."

    foreign_address = db.scalar(
        select(CustomerAddress).where(
            CustomerAddress.customer_id == customer_b.id,
        )
    )

    assert foreign_address is None



def test_get_order_status_returns_schedule_fields() -> None:
    db, store, registry = setup_registry()

    scheduled_for = datetime(
        2026, 8, 19, 23, 0, tzinfo=timezone.utc
    )
    release_at = datetime(
        2026, 8, 19, 22, 40, tzinfo=timezone.utc
    )

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000123",
        status="READY_FOR_INTEGRATION",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("30.00"),
        customer_name="Cliente Agendado",
        customer_phone="97999999999",
        scheduled_for=scheduled_for,
        release_at=release_at,
    )

    db.add(order)
    db.commit()

    result = registry.execute(
        "get_order_status",
        {
            "order_number": "123",
        },
    )

    assert result.ok is True
    assert result.data["display_id"] == "000123"
    assert result.data["is_scheduled"] is True

    assert (
        result.data["scheduled_for"]
        == scheduled_for.isoformat()
    )

    assert (
        result.data["release_at"]
        == release_at.isoformat()
    )



def test_checkout_blocks_reconstructed_duplicate_cart() -> None:
    db, store, _ = setup_registry()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597999112233",
        status="OPEN",
    )
    db.add(conversation)
    db.commit()

    registry = OliviaToolRegistry(
        ToolContext(
            db=db,
            store_id=store.id,
            conversation_id=conversation.id,
            customer_phone="5597999112233",
        )
    )

    customer = registry.execute(
        "find_or_create_customer",
        {
            "name": "Cliente Duplicidade",
            "phone": "5597999112233",
        },
    )

    first_cart = registry.execute(
        "get_or_create_cart",
        {
            "customer_id": customer.data["id"],
            "service_mode": "TAKEOUT",
        },
    )

    registry.execute(
        "add_cart_item",
        {
            "cart_id": first_cart.data["id"],
            "product_external_code": "235",
            "quantity": 1,
            "observations": "Sem cebola",
        },
    )

    first = registry.execute(
        "checkout_cart",
        {
            "cart_id": first_cart.data["id"],
            "payment_method": "PIX",
            "payment_type": "PENDING",
            "customer_confirmed": True,
        },
    )

    assert first.ok is True

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="checkout_cart",
            success=True,
            payload_json={
                "arguments": {
                    "cart_id": first_cart.data["id"],
                    "payment_method": "PIX",
                },
                "result": {
                    "ok": True,
                    "data": first.data,
                    "error": None,
                    "requires_human": False,
                },
            },
        )
    )
    db.commit()

    second_cart = registry.execute(
        "get_or_create_cart",
        {
            "customer_id": customer.data["id"],
            "service_mode": "TAKEOUT",
        },
    )

    assert second_cart.data["id"] != first_cart.data["id"]

    registry.execute(
        "add_cart_item",
        {
            "cart_id": second_cart.data["id"],
            "product_external_code": "235",
            "quantity": 1,
            "observations": "Sem cebola",
        },
    )

    second = registry.execute(
        "checkout_cart",
        {
            "cart_id": second_cart.data["id"],
            "payment_method": "PIX",
            "payment_type": "PENDING",
            "customer_confirmed": True,
        },
    )

    assert second.ok is True
    assert second.data["id"] == first.data["id"]
    assert second.data["display_id"] == first.data["display_id"]

    orders = list(
        db.scalars(
            select(Order).where(Order.store_id == store.id)
        )
    )
    assert len(orders) == 1


def test_checkout_allows_changed_cart_after_recent_order() -> None:
    db, store, _ = setup_registry()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597999445566",
        status="OPEN",
    )
    db.add(conversation)
    db.commit()

    registry = OliviaToolRegistry(
        ToolContext(
            db=db,
            store_id=store.id,
            conversation_id=conversation.id,
            customer_phone="5597999445566",
        )
    )

    customer = registry.execute(
        "find_or_create_customer",
        {
            "name": "Cliente Novo Pedido",
            "phone": "5597999445566",
        },
    )

    first_cart = registry.execute(
        "get_or_create_cart",
        {
            "customer_id": customer.data["id"],
            "service_mode": "TAKEOUT",
        },
    )

    registry.execute(
        "add_cart_item",
        {
            "cart_id": first_cart.data["id"],
            "product_external_code": "235",
            "quantity": 1,
        },
    )

    first = registry.execute(
        "checkout_cart",
        {
            "cart_id": first_cart.data["id"],
            "payment_method": "PIX",
            "payment_type": "PENDING",
            "customer_confirmed": True,
        },
    )

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="checkout_cart",
            success=True,
            payload_json={
                "result": {
                    "ok": True,
                    "data": first.data,
                    "error": None,
                    "requires_human": False,
                },
            },
        )
    )
    db.commit()

    second_cart = registry.execute(
        "get_or_create_cart",
        {
            "customer_id": customer.data["id"],
            "service_mode": "TAKEOUT",
        },
    )

    registry.execute(
        "add_cart_item",
        {
            "cart_id": second_cart.data["id"],
            "product_external_code": "235",
            "quantity": 2,
        },
    )

    second = registry.execute(
        "checkout_cart",
        {
            "cart_id": second_cart.data["id"],
            "payment_method": "PIX",
            "payment_type": "PENDING",
            "customer_confirmed": True,
        },
    )

    assert second.ok is True
    assert second.data["id"] != first.data["id"]

    orders = list(
        db.scalars(
            select(Order).where(Order.store_id == store.id)
        )
    )
    assert len(orders) == 2


def test_repeated_urgent_human_help_reuses_active_ticket():
    db, store, _ = setup_registry()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597999001122",
        status="OPEN",
    )
    db.add(conversation)
    db.commit()

    registry = OliviaToolRegistry(
        ToolContext(
            db=db,
            store_id=store.id,
            conversation_id=conversation.id,
            customer_phone="5597999001122",
        )
    )

    first = registry.execute(
        "request_human_help",
        {
            "reason": "Acidente com entregador",
            "customer_message": (
                "O entregador sofreu um acidente."
            ),
            "category": "OTHER",
            "priority": "URGENT",
            "create_knowledge_gap": False,
        },
    )

    assert first.ok is True
    assert first.data["reused_ticket"] is False

    second = registry.execute(
        "request_human_help",
        {
            "reason": (
                "Acidente com entregador; está no hospital"
            ),
            "customer_message": (
                "Ele está em observação no hospital."
            ),
            "category": "OTHER",
            "priority": "URGENT",
            "create_knowledge_gap": False,
        },
    )

    assert second.ok is True
    assert second.data["ticket_id"] == first.data["ticket_id"]
    assert second.data["reused_ticket"] is True
    assert second.data["escalation_already_active"] is True

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id == conversation.id
            )
        )
    )

    assert len(tickets) == 1
    assert tickets[0].priority == "URGENT"
    assert "hospital" in tickets[0].reason.lower()
    assert "hospital" in tickets[0].customer_message.lower()

    waiting_events = list(
        db.scalars(
            select(AIEvent).where(
                AIEvent.conversation_id == conversation.id,
                AIEvent.event_type == "HUMAN_WAITING",
            )
        )
    )

    assert len(waiting_events) == 1



def test_urgent_human_help_notifies_manager_only_on_first_escalation(
    monkeypatch,
):
    db, store, _ = setup_registry()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597999554433",
        status="OPEN",
    )
    db.add(conversation)
    db.commit()

    manager_calls = []

    class FakeManagerEscalation:
        def notify_conversation(self, db, **kwargs):
            manager_calls.append(kwargs)
            return 1

    monkeypatch.setattr(
        "app.ai.tools.support.ManagerEscalationService",
        FakeManagerEscalation,
    )

    registry = OliviaToolRegistry(
        ToolContext(
            db=db,
            store_id=store.id,
            conversation_id=conversation.id,
            customer_phone="5597999554433",
        )
    )

    first = registry.execute(
        "request_human_help",
        {
            "reason": "Entregador sofreu acidente",
            "customer_message": (
                "O entregador sofreu acidente e foi levado "
                "ao hospital."
            ),
            "category": "OTHER",
            "priority": "URGENT",
            "create_knowledge_gap": False,
        },
    )

    second = registry.execute(
        "request_human_help",
        {
            "reason": "Atualização do acidente",
            "customer_message": (
                "A bolsa de entrega ficou no hospital."
            ),
            "category": "OTHER",
            "priority": "URGENT",
            "create_knowledge_gap": False,
        },
    )

    assert first.ok is True
    assert first.data["manager_notified"] == 1
    assert first.data["escalation_already_active"] is False

    assert second.ok is True
    assert second.data["ticket_id"] == first.data["ticket_id"]
    assert second.data["reused_ticket"] is True
    assert second.data["manager_notified"] == 0
    assert second.data["escalation_already_active"] is True

    assert len(manager_calls) == 1
    assert manager_calls[0]["olivia_continues"] is False
    assert manager_calls[0]["source"] == (
        "REQUEST_HUMAN_HELP_URGENT"
    )


def test_olivia_prompt_has_critical_incident_mode():
    assert "INCIDENTES CRÍTICOS E SEGURANÇA" in OLIVIA_INSTRUCTIONS
    assert "priority=URGENT" in OLIVIA_INSTRUCTIONS
    assert "Não faça investigação clínica" in OLIVIA_INSTRUCTIONS
    assert "manager_notified" in OLIVIA_INSTRUCTIONS
    assert "não continue investigando" in OLIVIA_INSTRUCTIONS
