import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import app.models  # noqa: F401

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import (
    ChannelAccount,
    OutboundChannelMessage,
)
from app.models.conversation import AIEvent, Conversation
from app.models.staff import StoreStaffMember
from app.services.manager_escalation import (
    MANAGER_ALERT_TEMPLATE_NAME,
    ManagerEscalationService,
)


def _setup_manager(*, last_seen_at):
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
        external_account_id="phone-manager-test",
        display_phone_number="5597999999999",
        verify_token_hash="hash",
        active=True,
    )
    db.add(account)

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597977776666",
        status="OPEN",
    )
    db.add(conversation)

    manager = StoreStaffMember(
        store_id=store.id,
        name="Gerente Teste",
        phone="5597988882222",
        role="MANAGER",
        active=True,
        notify_whatsapp=True,
        last_seen_at=last_seen_at,
    )
    db.add(manager)

    db.commit()

    return db, store, account, conversation, manager


def test_manager_inside_window_receives_text_alert():
    now = datetime.now(timezone.utc)

    db, store, _, conversation, manager = _setup_manager(
        last_seen_at=now - timedelta(hours=1),
    )

    result = ManagerEscalationService().notify_conversation(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        title="Atendimento não assumido pela equipe",
        details=(
            "Nenhum atendente assumiu. "
            "A Olívia já retomou o atendimento."
        ),
        source="HUMAN_WAIT_TIMEOUT",
        now=now,
    )

    assert result == 1

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.recipient == manager.phone
        )
    )

    assert outbound is not None
    assert outbound.content_type == "TEXT"
    assert "Atendimento não assumido" in outbound.content
    assert "ASSUMIR" in outbound.content

    event = db.scalar(
        select(AIEvent).where(
            AIEvent.event_type == "MANAGER_ESCALATION"
        )
    )

    assert event is not None
    assert event.payload_json["source"] == "HUMAN_WAIT_TIMEOUT"


def test_manager_outside_window_receives_template_alert():
    now = datetime.now(timezone.utc)

    db, store, _, conversation, manager = _setup_manager(
        last_seen_at=now - timedelta(hours=24),
    )

    result = ManagerEscalationService().notify_conversation(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        title="Atendimento não assumido pela equipe",
        details=(
            "Nenhum atendente assumiu. "
            "A Olívia já retomou o atendimento."
        ),
        source="HUMAN_WAIT_TIMEOUT",
        now=now,
    )

    assert result == 1

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.recipient == manager.phone
        )
    )

    assert outbound is not None
    assert outbound.content_type == "TEMPLATE"

    payload = json.loads(outbound.content)

    assert payload["name"] == MANAGER_ALERT_TEMPLATE_NAME
    assert payload["language"]["code"] == "pt_BR"

    parameters = payload["components"][0]["parameters"]

    assert len(parameters) == 3
    assert parameters[0]["text"] == (
        "Atendimento não assumido pela equipe"
    )
    assert parameters[1]["text"].startswith("Conversa ")
    assert "ASSUMIR" in parameters[2]["text"]

    event = db.scalar(
        select(AIEvent).where(
            AIEvent.event_type == "MANAGER_ESCALATION"
        )
    )

    assert event is not None
    assert event.payload_json["source"] == "HUMAN_WAIT_TIMEOUT"
