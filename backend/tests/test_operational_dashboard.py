from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage
from app.models.conversation import AIEvent, Conversation, HumanTicket, KnowledgeGap
from app.models.customer import Customer
from app.models.cart import Cart
from app.models.order import Order
from app.services.operational_dashboard import OperationalDashboardService


def setup_db():
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

    customer = Customer(
        store_id=store.id,
        name="Cliente",
        phone="97999999999",
    )
    db.add(customer)
    db.flush()

    cart = Cart(
        store_id=store.id,
        customer_id=customer.id,
        status="CHECKED_OUT",
        service_mode="TAKEOUT",
    )
    db.add(cart)
    db.flush()

    db.add_all([
        Conversation(
            store_id=store.id,
            channel="WHATSAPP",
            external_conversation_id="551",
            status="OPEN",
        ),
        Conversation(
            store_id=store.id,
            channel="WHATSAPP",
            external_conversation_id="552",
            status="HUMAN",
        ),
        HumanTicket(
            store_id=store.id,
            category="CATALOG",
            priority="URGENT",
            status="OPEN",
            reason="Dúvida",
            customer_message="Mensagem",
        ),
        KnowledgeGap(
            store_id=store.id,
            question="Tem opção vegana?",
            normalized_question="tem opcao vegana?",
            status="OPEN",
            occurrences=3,
        ),
        AIEvent(
            store_id=store.id,
            event_type="AI_RESPONSE",
            success=True,
            duration_ms=100,
        ),
        AIEvent(
            store_id=store.id,
            event_type="TOOL_EXECUTION",
            success=False,
            duration_ms=300,
            error_message="Erro",
        ),
        Order(
            store_id=store.id,
            customer_id=customer.id,
            cart_id=cart.id,
            display_id="000001",
            status="PLACED",
            service_mode="TAKEOUT",
            payment_method="PIX",
            payment_type="PENDING",
            subtotal=Decimal("60.00"),
            delivery_fee=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=Decimal("60.00"),
            customer_name=customer.name,
            customer_phone=customer.phone,
        ),
    ])
    db.flush()

    account = ChannelAccount(
        store_id=store.id,
        provider="WHATSAPP_CLOUD",
        external_account_id="phone",
        verify_token_hash="hash",
        active=True,
    )
    db.add(account)
    db.flush()
    db.add_all([
        ChannelEvent(
            channel_account_id=account.id,
            provider=account.provider,
            external_event_id="event-retry",
            event_type="INBOUND_MESSAGE",
            status="RETRY",
            attempts=1,
            payload_json={},
        ),
        OutboundChannelMessage(
            channel_account_id=account.id,
            provider=account.provider,
            recipient="5597",
            content_type="TEXT",
            content="Olá",
            status="DEAD",
            attempts=5,
        ),
    ])
    db.commit()
    return db, store


def test_overview_summarizes_operations_and_alerts():
    db, store = setup_db()

    result = OperationalDashboardService().overview(
        db,
        store_id=store.id,
        hours=24,
    )

    assert result["conversations"]["open"] == 1
    assert result["conversations"]["human"] == 1
    assert result["tickets"]["urgent_active"] == 1
    assert result["orders"]["total"] == 1
    assert result["orders"]["revenue"] == 60.0
    assert result["ai"]["events"] == 2
    assert result["ai"]["errors"] == 1
    assert result["ai"]["average_duration_ms"] == 200.0
    assert result["queue"]["events_retry"] == 1
    assert result["queue"]["outbound_dead"] == 1

    codes = {alert["code"] for alert in result["alerts"]}
    assert "DEAD_QUEUE_ITEMS" in codes
    assert "QUEUE_RETRIES" in codes
    assert "URGENT_TICKETS" in codes
    assert "OPEN_KNOWLEDGE_GAPS" in codes
