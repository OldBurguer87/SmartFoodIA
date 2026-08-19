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
from app.services.human_relay import HumanRelayService


def _setup_escalated_conversation(*, event_age_minutes: int = 1):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    now = datetime.now(timezone.utc)

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
        external_account_id="phone-human-manager-test",
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
        last_message_at=now,
    )
    db.add(conversation)
    db.flush()

    event = AIEvent(
        store_id=store.id,
        conversation_id=conversation.id,
        event_type="MANAGER_ESCALATION",
        success=True,
        payload_json={
            "source": "TEST",
            "code": "776666",
            "notified": 1,
        },
        created_at=now - timedelta(minutes=event_age_minutes),
    )
    db.add(event)
    db.commit()

    return db, store, account, conversation


def _staff(
    db,
    *,
    store,
    name,
    phone,
    role,
):
    member = StoreStaffMember(
        store_id=store.id,
        name=name,
        phone=phone,
        role=role,
        active=True,
        notify_whatsapp=True,
    )
    db.add(member)
    db.commit()
    return member


def test_manager_can_assume_recently_escalated_open_conversation():
    db, store, account, conversation = (
        _setup_escalated_conversation(
            event_age_minutes=1,
        )
    )

    manager = _staff(
        db,
        store=store,
        name="Gerente Teste",
        phone="5597988882222",
        role="MANAGER",
    )

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=manager,
        body="ASSUMIR 776666",
    )

    db.refresh(conversation)
    db.refresh(manager)

    assert conversation.status == "HUMAN"
    assert manager.current_conversation_id == conversation.id

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.recipient == manager.phone
        )
    )

    assert outbound is not None
    assert "Atendimento 776666 assumido" in outbound.content


def test_attendant_cannot_assume_open_manager_escalation():
    db, store, account, conversation = (
        _setup_escalated_conversation(
            event_age_minutes=1,
        )
    )

    attendant = _staff(
        db,
        store=store,
        name="Atendente Teste",
        phone="5597988881111",
        role="ATTENDANT",
    )

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=attendant,
        body="ASSUMIR 776666",
    )

    db.refresh(conversation)
    db.refresh(attendant)

    assert conversation.status == "OPEN"
    assert attendant.current_conversation_id is None

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.recipient == attendant.phone
        )
    )

    assert outbound is not None
    assert "Não encontrei atendimento aguardando" in outbound.content


def test_manager_escalation_expires_after_30_minutes():
    db, store, account, conversation = (
        _setup_escalated_conversation(
            event_age_minutes=31,
        )
    )

    manager = _staff(
        db,
        store=store,
        name="Gerente Teste",
        phone="5597988882222",
        role="MANAGER",
    )

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=manager,
        body="ASSUMIR 776666",
    )

    db.refresh(conversation)
    db.refresh(manager)

    assert conversation.status == "OPEN"
    assert manager.current_conversation_id is None

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.recipient == manager.phone
        )
    )

    assert outbound is not None
    assert "Não encontrei atendimento aguardando" in outbound.content
