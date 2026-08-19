from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import app.models  # noqa: F401

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.conversation import Conversation
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.models.staff import StoreStaffMember
from app.services.pix_review_monitor import PixReviewMonitor


def _setup_rejected_pix():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    base = datetime.now(timezone.utc)

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
        external_account_id="phone-pix-monitor-test",
        display_phone_number="5597999999999",
        verify_token_hash="hash",
        active=True,
    )
    db.add(account)

    attendant = StoreStaffMember(
        store_id=store.id,
        name="Atendente Old",
        phone="5597988881111",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        last_seen_at=base,
    )
    db.add(attendant)

    manager = StoreStaffMember(
        store_id=store.id,
        name="Gerente Teste",
        phone="5597988882222",
        role="MANAGER",
        active=True,
        notify_whatsapp=True,
        last_seen_at=base,
    )
    db.add(manager)

    customer_phone = "5597977776666"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000777",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name="Cliente Teste",
        customer_phone=customer_phone,
    )
    db.add(order)
    db.flush()

    receipt = PaymentReceipt(
        store_id=store.id,
        order_id=order.id,
        conversation_id=conversation.id,
        external_media_id="media-rejected-monitor",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256="a" * 64,
        status="HUMAN_REJECTED",
        reviewed_by="Atendente Teste via WhatsApp",
        reviewed_at=base,
        review_notes="Comprovante recusado para teste.",
        validation_json={},
    )
    db.add(receipt)
    db.commit()

    return {
        "db": db,
        "base": base,
        "store": store,
        "account": account,
        "attendant": attendant,
        "manager": manager,
        "customer_phone": customer_phone,
        "conversation": conversation,
        "order": order,
        "receipt": receipt,
    }


def _outbound_for(db, phone):
    return list(
        db.scalars(
            select(OutboundChannelMessage)
            .where(OutboundChannelMessage.recipient == phone)
            .order_by(OutboundChannelMessage.created_at)
        ).all()
    )


def test_rejected_pix_follows_5_10_15_minute_chain_once():
    ctx = _setup_rejected_pix()
    db = ctx["db"]
    base = ctx["base"]
    receipt = ctx["receipt"]

    monitor = PixReviewMonitor()

    # 4m59s: nada ainda.
    result = monitor.run_once(
        db,
        now=base + timedelta(seconds=299),
    )

    assert result.rejected_customer_reminders == 0
    assert result.rejected_staff_alerts == 0
    assert result.rejected_final_alerts == 0

    assert _outbound_for(db, ctx["customer_phone"]) == []
    assert _outbound_for(db, ctx["attendant"].phone) == []
    assert _outbound_for(db, ctx["manager"].phone) == []

    # 5 min: somente cliente.
    result = monitor.run_once(
        db,
        now=base + timedelta(seconds=300),
    )

    assert result.rejected_customer_reminders == 1
    assert result.rejected_staff_alerts == 0
    assert result.rejected_final_alerts == 0

    customer_messages = _outbound_for(
        db,
        ctx["customer_phone"],
    )

    assert len(customer_messages) == 1
    assert "Ainda estamos aguardando" in customer_messages[0].content
    assert "novo comprovante PIX" in customer_messages[0].content

    assert _outbound_for(db, ctx["attendant"].phone) == []
    assert _outbound_for(db, ctx["manager"].phone) == []

    # 10 min: somente atendente.
    result = monitor.run_once(
        db,
        now=base + timedelta(seconds=600),
    )

    assert result.rejected_customer_reminders == 0
    assert result.rejected_staff_alerts == 1
    assert result.rejected_final_alerts == 0

    attendant_messages = _outbound_for(
        db,
        ctx["attendant"].phone,
    )

    assert len(attendant_messages) == 1
    assert "PIX continua pendente" in attendant_messages[0].content
    assert "#000777" in attendant_messages[0].content

    assert len(
        _outbound_for(db, ctx["customer_phone"])
    ) == 1

    assert _outbound_for(db, ctx["manager"].phone) == []

    # 15 min: somente gerente.
    result = monitor.run_once(
        db,
        now=base + timedelta(seconds=900),
    )

    assert result.rejected_customer_reminders == 0
    assert result.rejected_staff_alerts == 0
    assert result.rejected_final_alerts == 1

    manager_messages = _outbound_for(
        db,
        ctx["manager"].phone,
    )

    assert len(manager_messages) == 1
    assert "PIX ainda pendente" in manager_messages[0].content
    assert "#000777" in manager_messages[0].content
    assert "não cancelou" in manager_messages[0].content

    # Nova execução não pode repetir nada.
    before_total = len(
        list(db.scalars(select(OutboundChannelMessage)).all())
    )

    result = monitor.run_once(
        db,
        now=base + timedelta(seconds=1200),
    )

    after_total = len(
        list(db.scalars(select(OutboundChannelMessage)).all())
    )

    assert result.rejected_customer_reminders == 0
    assert result.rejected_staff_alerts == 0
    assert result.rejected_final_alerts == 0
    assert after_total == before_total

    db.refresh(receipt)

    validation = receipt.validation_json or {}

    assert validation["rejected_customer_reminded"] is True
    assert validation["rejected_staff_alerted"] is True
    assert validation["rejected_staff_final_alerted"] is True


def test_new_pix_receipt_stops_old_rejection_escalation():
    ctx = _setup_rejected_pix()
    db = ctx["db"]
    base = ctx["base"]
    old_receipt = ctx["receipt"]

    newer = PaymentReceipt(
        store_id=ctx["store"].id,
        order_id=ctx["order"].id,
        conversation_id=ctx["conversation"].id,
        external_media_id="media-new-receipt",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256="b" * 64,
        status="RECEIVED",
        validation_json={},
    )

    # Torna a ordenação temporal determinística.
    newer.created_at = base + timedelta(seconds=1)

    db.add(newer)
    db.commit()

    result = PixReviewMonitor().run_once(
        db,
        now=base + timedelta(seconds=900),
    )

    assert result.rejected_customer_reminders == 0
    assert result.rejected_staff_alerts == 0
    assert result.rejected_final_alerts == 0

    messages = list(
        db.scalars(select(OutboundChannelMessage)).all()
    )

    assert messages == []

    db.refresh(old_receipt)

    validation = old_receipt.validation_json or {}

    assert not validation.get("rejected_customer_reminded")
    assert not validation.get("rejected_staff_alerted")
    assert not validation.get("rejected_staff_final_alerted")
