from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.channels.whatsapp.service import WhatsAppGatewayService
from app.core.config import settings
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.conversation import AIEvent, Message
from app.repositories.channel import ChannelRepository
from app.schemas.conversation import ConversationCreate
from app.services.conversation import ConversationService
from app.services.handoff_monitor import HumanHandoffMonitor


class FailingOrchestrator:
    def reply(self, *args, **kwargs):
        raise AssertionError("A Olívia não deveria ser chamada em modo humano.")


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
    account = ChannelAccount(
        store_id=store.id,
        provider="WHATSAPP_CLOUD",
        external_account_id="phone-123",
        display_phone_number="97999999999",
        verify_token_hash="hash",
        active=True,
    )
    db.add(account)
    db.commit()
    conversation = ConversationService().get_or_create(
        db,
        ConversationCreate(
            store_id=store.id,
            channel="WHATSAPP",
            external_conversation_id="5597991112222",
        ),
    )
    return db, store, account, conversation


def test_takeover_and_release_record_events():
    db, _, _, conversation = setup_context()
    service = ConversationService()

    taken = service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente 1",
    )
    assert taken.status == "HUMAN"

    released = service.release_to_olivia(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente 1",
    )
    assert released.status == "OPEN"

    events = list(db.scalars(select(AIEvent).where(
        AIEvent.conversation_id == conversation.id
    )))
    assert {event.event_type for event in events} == {
        "HUMAN_TAKEOVER",
        "HUMAN_RELEASE",
    }


def test_inbound_message_does_not_call_olivia_during_takeover():
    db, _, account, conversation = setup_context()
    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )
    repository = ChannelRepository()
    event = repository.create_event(
        db,
        account=account,
        external_event_id="wamid-1",
        event_type="INBOUND_MESSAGE",
        payload={
            "id": "wamid-1",
            "from": "5597991112222",
            "type": "text",
            "text": {"body": "Preciso de ajuda"},
        },
    )

    WhatsAppGatewayService(
        repository=repository,
        orchestrator_factory=lambda: FailingOrchestrator(),
    ).process_event(db, account, event)

    messages = list(db.scalars(select(Message).where(
        Message.conversation_id == conversation.id
    )))
    assert len(messages) == 1
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[0].content == "Preciso de ajuda"


def test_human_reply_is_persisted_and_queued():
    db, _, account, conversation = setup_context()
    service = ConversationService()
    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )
    message = service.add_human_message(
        db,
        conversation_id=conversation.id,
        content="Olá, vou ajudar você.",
        assigned_to="Atendente",
    )
    outbound = ChannelRepository().create_outbound(
        db,
        account=account,
        conversation_id=conversation.id,
        recipient=conversation.external_conversation_id,
        content=message.content,
    )

    assert message.sender_type == "HUMAN"
    assert outbound.status == "PENDING"
    assert db.get(OutboundChannelMessage, outbound.id) is not None


def test_handoff_timeout_resumes_before_staff_availability_check():
    db, store, _, conversation = setup_context()

    conversation.status = "WAITING_HUMAN"

    wait_event = AIEvent(
        store_id=store.id,
        conversation_id=conversation.id,
        event_type="HUMAN_WAITING",
        success=True,
        payload_json={"reason": "cliente pediu atendente"},
    )
    db.add(wait_event)
    db.commit()
    db.refresh(wait_event)

    class FakeResumeOrchestrator:
        def reply(self, *args, **kwargs):
            return "Não consegui falar com a equipe a tempo. Voltei para ajudar."

    monitor = HumanHandoffMonitor(
        orchestrator_factory=lambda: FakeResumeOrchestrator()
    )

    def fail_if_staff_availability_is_checked(*args, **kwargs):
        raise AssertionError(
            "A disponibilidade da equipe não deve impedir o timeout."
        )

    monitor.relay.staff_is_available_now = (
        fail_if_staff_availability_is_checked
    )
    monitor.relay.notify_timeout = lambda *args, **kwargs: None

    now = wait_event.created_at + timedelta(
        seconds=settings.human_wait_timeout_seconds + 1
    )

    result = monitor.run_once(db, now=now)

    db.refresh(conversation)

    assert result.resumed == 1
    assert result.failed == 0
    assert conversation.status == "OPEN"

    timeout_event = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "HUMAN_WAIT_TIMEOUT",
        )
    )
    assert timeout_event is not None
