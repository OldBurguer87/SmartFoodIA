from decimal import Decimal
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.base import ProviderResponse, ProviderToolCall
from app.database.base import Base
from app.models.catalog import Company, Product, Store
from app.models.conversation import AIEvent, Message
from app.schemas.conversation import ConversationCreate
from app.services.conversation import ConversationService

class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def respond(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

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
    db.add(Product(
        store_id=store.id,
        external_code="235",
        name="Old Monster",
        description="Hambúrguer artesanal",
        price=Decimal("60.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    ))
    db.commit()
    conversation = ConversationService().get_or_create(
        db,
        ConversationCreate(
            store_id=store.id,
            channel="WHATSAPP",
            external_conversation_id="wa-test",
        ),
    )
    return db, store, conversation

def test_orchestrator_executes_tool_then_returns_text():
    db, store, conversation = setup_context()
    provider = FakeProvider([
        ProviderResponse(
            response_id="resp-1",
            tool_calls=[ProviderToolCall(
                call_id="call-1",
                name="search_catalog",
                arguments={"query": "monster", "service_mode": "DELIVERY", "limit": 10},
            )],
        ),
        ProviderResponse(response_id="resp-2", text="Temos o Old Monster por R$ 60,00."),
    ])
    reply = OliviaOrchestrator(provider).reply(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        customer_message="Tem Monster?",
        customer_phone="97999999999",
    )
    assert reply.startswith(
        ("Bom dia!", "Boa tarde!", "Boa noite!")
    )
    assert reply.endswith(
        "Temos o Old Monster por R$ 60,00."
    )
    assert provider.calls[1]["previous_response_id"] == "resp-1"
    assert provider.calls[1]["input_items"][0]["type"] == "function_call_output"
    messages = list(db.scalars(select(Message).where(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at)))
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[-1].sender_type == "OLIVIA"
    events = list(db.scalars(select(AIEvent).where(
        AIEvent.conversation_id == conversation.id
    )))
    assert any(event.event_type == "TOOL_EXECUTION" for event in events)

def test_orchestrator_returns_direct_response_without_tool():
    db, store, conversation = setup_context()
    provider = FakeProvider([
        ProviderResponse(response_id="resp-1", text="Olá! Como posso ajudar?")
    ])
    reply = OliviaOrchestrator(provider).reply(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        customer_message="Oi",
    )
    assert reply.startswith(
        ("Bom dia!", "Boa tarde!", "Boa noite!")
    )
    assert reply.endswith(
        "Olá! Como posso ajudar?"
    )
