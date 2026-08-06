from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.tools.context import ToolContext
from app.ai.tools.support import RequestHumanHelpTool
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.conversation import AIEvent, HumanTicket, KnowledgeGap, Message
from app.schemas.conversation import (
    AIEventCreate,
    ConversationCreate,
    KnowledgeGapCreate,
    KnowledgeGapResolve,
    MessageCreate,
)
from app.services.conversation import ConversationService


def setup_db() -> tuple[Session, Store]:
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
    db.commit()
    db.refresh(store)
    return db, store


def test_conversation_is_reused_by_channel_and_external_id() -> None:
    db, store = setup_db()
    service = ConversationService()
    payload = ConversationCreate(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="wa-123",
    )

    first = service.get_or_create(db, payload)
    second = service.get_or_create(db, payload)

    assert first.id == second.id


def test_messages_are_persisted() -> None:
    db, store = setup_db()
    service = ConversationService()
    conversation = service.get_or_create(
        db,
        ConversationCreate(
            store_id=store.id,
            channel="WHATSAPP",
            external_conversation_id="wa-456",
        ),
    )

    message = service.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="INBOUND",
            sender_type="CUSTOMER",
            content="Quero um Old Monster",
        ),
    )

    persisted = db.scalar(select(Message).where(Message.id == message.id))
    assert persisted.content == "Quero um Old Monster"


def test_knowledge_gap_is_incremented_for_same_question() -> None:
    db, store = setup_db()
    service = ConversationService()
    first = service.create_or_increment_gap(
        db,
        store_id=store.id,
        payload=KnowledgeGapCreate(
            question="O molho barbecue é artesanal?"
        ),
    )
    second = service.create_or_increment_gap(
        db,
        store_id=store.id,
        payload=KnowledgeGapCreate(
            question="o molho barbecue e artesanal?"
        ),
    )

    assert first.id == second.id
    assert second.occurrences == 2


def test_knowledge_gap_can_be_resolved() -> None:
    db, store = setup_db()
    service = ConversationService()
    gap = service.create_or_increment_gap(
        db,
        store_id=store.id,
        payload=KnowledgeGapCreate(question="Tem opção sem lactose?"),
    )

    resolved = service.resolve_gap(
        db,
        gap_id=gap.id,
        payload=KnowledgeGapResolve(
            answer="No momento, não temos opção sem lactose."
        ),
    )

    assert resolved.status == "RESOLVED"
    assert "não temos" in resolved.answer


def test_human_help_tool_persists_ticket_and_gap() -> None:
    db, store = setup_db()
    tool = RequestHumanHelpTool(
        ToolContext(
            db=db,
            store_id=store.id,
            customer_phone="97999999999",
        )
    )

    result = tool.execute(
        reason="Informação não confirmada",
        customer_message="O molho barbecue é artesanal?",
        category="CATALOG",
    )

    assert result.ok is True
    assert result.requires_human is True
    assert db.get(HumanTicket, UUID(result.data["ticket_id"])) is not None
    assert db.get(KnowledgeGap, UUID(result.data["knowledge_gap_id"])) is not None


def test_ai_event_is_persisted() -> None:
    db, store = setup_db()
    event = ConversationService().record_event(
        db,
        store_id=store.id,
        payload=AIEventCreate(
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            duration_ms=42,
            payload_json={"query": "monster"},
        ),
    )

    persisted = db.get(AIEvent, event.id)
    assert persisted.tool_name == "search_catalog"
    assert persisted.duration_ms == 42
