from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import app.models  # noqa: F401

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.commercial import StoreBusinessHours
from app.models.conversation import Conversation
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.models.staff import StoreStaffMember
from app.services.pix_receipt_review import PixReceiptReviewService


def test_pix_review_notifies_staff_even_when_store_is_closed():
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

    # Loja fechada em todos os dias:
    # a revisão PIX não deve depender desse horário.
    for weekday in range(7):
        db.add(
            StoreBusinessHours(
                store_id=store.id,
                weekday=weekday,
                closed=True,
            )
        )

    account = ChannelAccount(
        store_id=store.id,
        provider="WHATSAPP_CLOUD",
        external_account_id="phone-review-test",
        display_phone_number="5597999999999",
        verify_token_hash="hash",
        active=True,
    )
    db.add(account)

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone="5597988887777",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(staff)

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000123",
        status="PLACED",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("7.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("7.00"),
        customer_name="Cliente Teste",
        customer_phone="5597977776666",
    )
    db.add(order)
    db.flush()

    receipt = PaymentReceipt(
        store_id=store.id,
        order_id=order.id,
        external_media_id="media-review-test",
        media_type="IMAGE",
        mime_type="image/png",
        storage_path="/tmp/comprovante-inexistente-teste.png",
        file_sha256="c" * 64,
        status="NEEDS_REVIEW",
        extracted_amount=Decimal("7.00"),
        extracted_transaction_id="E2E-REVIEW-123",
        extracted_transaction_status="CONCLUIDO",
        validation_json={
            "reasons": [
                "DUPLICATE_TRANSACTION_ID",
            ],
        },
    )
    db.add(receipt)
    db.commit()

    service = PixReceiptReviewService()

    notified = service.notify_review(
        db,
        account=account,
        receipt=receipt,
    )

    outbound = list(
        db.scalars(
            select(OutboundChannelMessage).where(
                OutboundChannelMessage.recipient == staff.phone
            )
        )
    )

    assert notified == 1
    assert len(outbound) == 1
    assert "PIX precisa de conferência" in outbound[0].content
    assert "ID/E2E do PIX já foi usado antes" in outbound[0].content



def test_reject_duplicate_pix_sends_specific_customer_warning():
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
        external_account_id="phone-reject-test",
        display_phone_number="5597999999999",
        verify_token_hash="hash",
        active=True,
    )
    db.add(account)

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone="5597988887777",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(staff)

    customer_phone = "5597977776666"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="OPEN",
    )
    db.add(conversation)

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000124",
        status="READY_FOR_INTEGRATION",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("7.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("7.00"),
        customer_name="Cliente Duplicidade",
        customer_phone=customer_phone,
    )
    db.add(order)
    db.flush()

    receipt = PaymentReceipt(
        store_id=store.id,
        order_id=order.id,
        conversation_id=conversation.id,
        external_media_id="media-duplicate-reject",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256="d" * 64,
        status="NEEDS_REVIEW",
        extracted_transaction_id="E2E-DUPLICADO-REJECT",
        validation_json={
            "reasons": [
                "DUPLICATE_TRANSACTION_ID",
            ],
        },
    )
    db.add(receipt)
    db.commit()

    service = PixReceiptReviewService()

    staff_response = service.reject(
        db,
        account=account,
        staff=staff,
        display_id="000124",
    )

    db.refresh(receipt)

    outbound = list(
        db.scalars(
            select(OutboundChannelMessage).where(
                OutboundChannelMessage.recipient == customer_phone
            )
        )
    )

    assert receipt.status == "HUMAN_REJECTED"

    assert len(outbound) == 1

    customer_message = outbound[0].content

    assert "Essa transação já foi utilizada anteriormente" in (
        customer_message
    )

    assert "não pode ser usada para confirmar este pedido" in (
        customer_message
    )

    assert "Se você realizou um novo PIX" in customer_message

    assert "Pode enviar o comprovante novamente" not in (
        customer_message
    )

    assert (
        "O cliente foi orientado sobre o comprovante."
        in staff_response
    )
