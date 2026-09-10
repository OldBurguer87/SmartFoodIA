import json
from io import BytesIO

import pytest
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers, UploadFile

import app.api.operations as operations_api
from app.channels.whatsapp.service import WhatsAppGatewayService
from app.core.config import settings
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.cart import Cart
from app.models.customer import Customer
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.conversation import AIEvent, HumanTicket, Message
from app.models.staff import StoreStaffMember
from app.repositories.channel import ChannelRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationTakeoverRequest,
    HumanTicketCreate,
)
from app.services.conversation import (
    ConversationService,
    ConversationStateError,
)
from app.services.conversation_media import ConversationMediaStorage
from app.services.handoff_monitor import HumanHandoffMonitor
from app.services.human_relay import HumanRelayService


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
        "ORDER_COLLECTION_STATE",
        "HUMAN_TAKEOVER",
        "HUMAN_RELEASE",
    }

    collection_state = next(
        event
        for event in events
        if event.event_type == "ORDER_COLLECTION_STATE"
    )

    assert collection_state.payload_json["state"] == "NORMAL"
    assert (
        collection_state.payload_json["reason"]
        == "human_takeover"
    )


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


def test_handoff_timeout_resumes_before_staff_availability_check(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "human_only_mode",
        False,
    )
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



def test_urgent_handoff_never_resumes_olivia_on_timeout():
    db, store, _, conversation = setup_context()

    conversation.status = "WAITING_HUMAN"

    ticket = HumanTicket(
        store_id=store.id,
        conversation_id=conversation.id,
        category="OTHER",
        priority="URGENT",
        status="OPEN",
        reason="Acidente com entregador; atendimento humano necessário",
        customer_message="O entregador sofreu um acidente.",
    )
    db.add(ticket)

    wait_event = AIEvent(
        store_id=store.id,
        conversation_id=conversation.id,
        event_type="HUMAN_WAITING",
        success=True,
        payload_json={
            "reason": (
                "Acidente com entregador; "
                "atendimento humano necessário"
            ),
            "ticket_id": str(ticket.id),
        },
    )
    db.add(wait_event)
    db.commit()
    db.refresh(wait_event)

    monitor = HumanHandoffMonitor(
        orchestrator_factory=lambda: FailingOrchestrator()
    )

    # Depois do timeout máximo, um chamado URGENT continua humano.
    now = wait_event.created_at + timedelta(
        seconds=settings.human_wait_timeout_seconds + 60
    )

    result = monitor.run_once(
        db,
        now=now,
    )

    db.refresh(conversation)

    assert result.resumed == 0
    assert result.failed == 0
    assert conversation.status == "WAITING_HUMAN"

    timeout_event = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "HUMAN_WAIT_TIMEOUT",
        )
    )

    assert timeout_event is None


def test_human_only_mode_never_resumes_olivia_on_timeout(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", True)

    db, store, _, conversation = setup_context()
    conversation.status = "WAITING_HUMAN"

    wait_event = AIEvent(
        store_id=store.id,
        conversation_id=conversation.id,
        event_type="HUMAN_WAITING",
        success=True,
        payload_json={"reason": "modo 100% humano"},
    )
    db.add(wait_event)
    db.commit()
    db.refresh(wait_event)

    # Se o monitor tentar chamar a Olivia, este orchestrator faz o teste falhar.
    monitor = HumanHandoffMonitor(
        orchestrator_factory=lambda: FailingOrchestrator()
    )

    now = wait_event.created_at + timedelta(
        seconds=settings.human_wait_timeout_seconds + 60
    )

    result = monitor.run_once(
        db,
        now=now,
    )

    db.refresh(conversation)

    assert result.resumed == 0
    assert result.failed == 0
    assert conversation.status == "WAITING_HUMAN"

    timeout_event = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "HUMAN_WAIT_TIMEOUT",
        )
    )
    assert timeout_event is None



def test_close_human_conversation_resolves_ticket_and_releases_staff():
    db, store, _, conversation = setup_context()
    service = ConversationService()

    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente Teste",
    )

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone="5597988877665",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        current_conversation_id=conversation.id,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)

    ticket = service.create_ticket(
        db,
        store_id=store.id,
        payload=HumanTicketCreate(
            conversation_id=conversation.id,
            category="OTHER",
            priority="URGENT",
            reason="Atendimento humano",
            customer_message="Preciso de ajuda",
        ),
    )

    service.assign_ticket(
        db,
        ticket_id=ticket.id,
        assigned_to="Atendente Teste",
    )

    closed = service.close_human_conversation(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente Teste",
    )

    db.refresh(staff)
    db.refresh(ticket)

    assert closed.status == "CLOSED"
    assert staff.current_conversation_id is None

    assert ticket.status == "RESOLVED"
    assert ticket.assigned_to == "Atendente Teste"
    assert ticket.resolution == (
        "Atendimento humano finalizado."
    )

    events = list(
        db.scalars(
            select(AIEvent).where(
                AIEvent.conversation_id
                == conversation.id
            )
        )
    )

    assert "HUMAN_CLOSED" in {
        event.event_type
        for event in events
    }


def test_close_human_conversation_rejects_non_human():
    db, _, _, conversation = setup_context()
    service = ConversationService()

    with pytest.raises(ConversationStateError):
        service.close_human_conversation(
            db,
            conversation_id=conversation.id,
            assigned_to="Atendente Teste",
        )

    db.refresh(conversation)

    assert conversation.status == "OPEN"



def test_human_pdf_upload_is_stored_and_queued(
    tmp_path,
    monkeypatch,
):
    db, _, _, conversation = setup_context()

    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    monkeypatch.setattr(
        operations_api,
        "ConversationMediaStorage",
        lambda: ConversationMediaStorage(
            root_path=tmp_path,
            max_bytes=1024 * 1024,
        ),
    )

    pdf_bytes = b"%PDF-1.4\n% SmartFoodIA teste\n%%EOF\n"

    upload = UploadFile(
        file=BytesIO(pdf_bytes),
        filename="cardapio.pdf",
        headers=Headers(
            {
                "content-type": "application/pdf",
            }
        ),
    )

    result = operations_api.human_media_reply(
        conversation_id=conversation.id,
        file=upload,
        assigned_to="Atendente",
        caption="Segue nosso cardápio.",
        _access=None,
        db=db,
    )

    message = db.get(
        Message,
        UUID(result["message_id"]),
    )

    assert message is not None
    assert message.sender_type == "HUMAN"
    assert message.direction == "OUTBOUND"
    assert message.content_type == "DOCUMENT"
    assert message.content == "Segue nosso cardápio."

    metadata = message.metadata_json

    assert metadata["source"] == "HUMAN_UPLOAD"
    assert metadata["assigned_to"] == "Atendente"
    assert metadata["stored_media"] is True
    assert metadata["mime_type"] == "application/pdf"
    assert metadata["filename"] == "cardapio.pdf"
    assert metadata["media_type"] == "document"
    assert metadata["file_size"] == len(pdf_bytes)

    stored_path = (
        tmp_path
        / metadata["stored_media_path"]
    )

    assert stored_path.is_file()
    assert stored_path.read_bytes() == pdf_bytes

    outbound = db.get(
        OutboundChannelMessage,
        UUID(result["outbound_id"]),
    )

    assert outbound is not None
    assert outbound.content_type == "MEDIA_FILE"
    assert outbound.status == "PENDING"
    assert outbound.external_message_id is None
    assert outbound.recipient == "5597991112222"

    queued = json.loads(outbound.content)

    assert queued["path"] == str(stored_path)
    assert queued["mime_type"] == "application/pdf"
    assert queued["media_type"] == "document"
    assert queued["filename"] == "cardapio.pdf"
    assert queued["caption"] == "Segue nosso cardápio."

def test_human_pix_confirmation_uses_real_customer_media(
    tmp_path,
    monkeypatch,
):
    db, store, _, conversation = setup_context()
    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    customer = Customer(
        store_id=store.id,
        name="Cliente PIX",
        phone="5597991112222",
    )
    db.add(customer)
    db.flush()
    conversation.customer_id = customer.id

    cart = Cart(
        store_id=store.id,
        customer_id=customer.id,
        status="CHECKED_OUT",
        service_mode="DELIVERY",
    )
    db.add(cart)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=cart.id,
        display_id="000901",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="MIXED",
        payment_type="PENDING",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name=customer.name,
        customer_phone=customer.phone,
    )
    db.add(order)
    db.flush()

    from app.models.order import OrderPayment

    db.add_all(
        [
            OrderPayment(
                order_id=order.id,
                method="PIX",
                payment_type="PREPAID",
                amount=Decimal("20.00"),
                position=1,
            ),
            OrderPayment(
                order_id=order.id,
                method="CASH",
                payment_type="PENDING",
                amount=Decimal("15.00"),
                position=2,
            ),
        ]
    )
    db.flush()

    media_root = tmp_path / "conversation-media"
    receipt_root = tmp_path / "receipts"
    storage = ConversationMediaStorage(
        root_path=media_root,
        max_bytes=1024 * 1024,
    )
    content = b"%PDF-1.4\n% PIX manual teste\n%%EOF\n"
    stored = storage.store(
        store_id=store.id,
        conversation_id=conversation.id,
        content=content,
        mime_type="application/pdf",
        original_filename="pix.pdf",
    )

    message = Message(
        conversation_id=conversation.id,
        direction="INBOUND",
        sender_type="CUSTOMER",
        content_type="DOCUMENT",
        content="[Documento recebido: pix.pdf]",
        metadata_json={
            "media_id": "media-pix-test",
            "stored_media": True,
            "stored_media_path": stored.relative_path,
            "mime_type": stored.mime_type,
            "file_size": stored.file_size,
            "sha256": stored.sha256,
            "filename": "pix.pdf",
        },
    )
    db.add(message)
    db.commit()

    monkeypatch.setattr(
        operations_api,
        "ConversationMediaStorage",
        lambda: ConversationMediaStorage(
            root_path=media_root,
            max_bytes=1024 * 1024,
        ),
    )
    monkeypatch.setattr(
        settings,
        "payment_receipt_storage_path",
        str(receipt_root),
    )

    result = operations_api.confirm_human_pix(
        conversation_id=conversation.id,
        order_id=order.id,
        message_id=message.id,
        assigned_to="Atendente",
        _access=None,
        db=db,
    )

    receipt = db.get(
        PaymentReceipt,
        UUID(result["receipt_id"]),
    )
    assert receipt is not None
    assert receipt.order_id == order.id
    assert receipt.conversation_id == conversation.id
    assert receipt.status == "HUMAN_CONFIRMED"
    assert receipt.file_sha256 == stored.sha256
    assert receipt.mime_type == "application/pdf"
    assert receipt.reviewed_by == "Atendente via Central Web"
    assert open(receipt.storage_path, "rb").read() == content
    assert str(receipt_root) in receipt.storage_path
    assert result["already_confirmed"] is False

    db.refresh(message)
    assert message.metadata_json["payment_receipt_id"] == str(receipt.id)
    assert message.metadata_json["payment_receipt_status"] == "HUMAN_CONFIRMED"
    assert receipt.validation_json["source_message_id"] == str(message.id)

def test_human_pix_confirmation_rejects_receipt_reuse(
    tmp_path,
    monkeypatch,
):
    db, store, _, conversation = setup_context()
    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    customer = Customer(
        store_id=store.id,
        name="Cliente PIX",
        phone="5597991112222",
    )
    db.add(customer)
    db.flush()
    conversation.customer_id = customer.id

    def make_order(display_id):
        cart = Cart(
            store_id=store.id,
            customer_id=customer.id,
            status="CHECKED_OUT",
            service_mode="DELIVERY",
        )
        db.add(cart)
        db.flush()
        order = Order(
            store_id=store.id,
            customer_id=customer.id,
            cart_id=cart.id,
            display_id=display_id,
            status="READY_FOR_INTEGRATION",
            service_mode="DELIVERY",
            payment_method="PIX",
            payment_type="PREPAID",
            subtotal=Decimal("30.00"),
            delivery_fee=Decimal("5.00"),
            discount=Decimal("0.00"),
            total=Decimal("35.00"),
            customer_name=customer.name,
            customer_phone=customer.phone,
        )
        db.add(order)
        db.flush()
        return order

    first_order = make_order("000902")
    second_order = make_order("000903")

    media_root = tmp_path / "conversation-media"
    receipt_root = tmp_path / "receipts"
    storage = ConversationMediaStorage(
        root_path=media_root,
        max_bytes=1024 * 1024,
    )
    content = b"%PDF-1.4\n% PIX reutilizacao\n%%EOF\n"
    stored = storage.store(
        store_id=store.id,
        conversation_id=conversation.id,
        content=content,
        mime_type="application/pdf",
        original_filename="pix-unico.pdf",
    )

    message = Message(
        conversation_id=conversation.id,
        direction="INBOUND",
        sender_type="CUSTOMER",
        content_type="DOCUMENT",
        content="[Documento recebido: pix-unico.pdf]",
        metadata_json={
            "media_id": "media-pix-unico",
            "stored_media": True,
            "stored_media_path": stored.relative_path,
            "mime_type": stored.mime_type,
            "file_size": stored.file_size,
            "sha256": stored.sha256,
            "filename": "pix-unico.pdf",
        },
    )
    db.add(message)
    db.commit()

    monkeypatch.setattr(
        operations_api,
        "ConversationMediaStorage",
        lambda: ConversationMediaStorage(
            root_path=media_root,
            max_bytes=1024 * 1024,
        ),
    )
    monkeypatch.setattr(
        settings,
        "payment_receipt_storage_path",
        str(receipt_root),
    )

    first = operations_api.confirm_human_pix(
        conversation_id=conversation.id,
        order_id=first_order.id,
        message_id=message.id,
        assigned_to="Atendente",
        _access=None,
        db=db,
    )
    assert first["status"] == "HUMAN_CONFIRMED"

    with pytest.raises(operations_api.HTTPException) as error:
        operations_api.confirm_human_pix(
            conversation_id=conversation.id,
            order_id=second_order.id,
            message_id=message.id,
            assigned_to="Atendente",
            _access=None,
            db=db,
        )

    assert error.value.status_code == 422
    assert "outro pedido" in str(error.value.detail)

    second_receipt = db.scalar(
        select(PaymentReceipt).where(
            PaymentReceipt.order_id == second_order.id
        )
    )
    assert second_receipt is None

def test_human_pix_confirmation_rejects_other_customer(
    tmp_path,
    monkeypatch,
):
    db, store, _, conversation = setup_context()
    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    customer_a = Customer(
        store_id=store.id,
        name="Cliente A",
        phone="5597991112222",
    )
    customer_b = Customer(
        store_id=store.id,
        name="Cliente B",
        phone="5597999998888",
    )
    db.add_all([customer_a, customer_b])
    db.flush()
    conversation.customer_id = customer_a.id

    cart = Cart(
        store_id=store.id,
        customer_id=customer_b.id,
        status="CHECKED_OUT",
        service_mode="DELIVERY",
    )
    db.add(cart)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=customer_b.id,
        cart_id=cart.id,
        display_id="000904",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name=customer_b.name,
        customer_phone=customer_b.phone,
    )
    db.add(order)
    db.flush()

    media_root = tmp_path / "conversation-media"
    receipt_root = tmp_path / "receipts"
    storage = ConversationMediaStorage(
        root_path=media_root,
        max_bytes=1024 * 1024,
    )
    content = b"%PDF-1.4\n% PIX cliente A\n%%EOF\n"
    stored = storage.store(
        store_id=store.id,
        conversation_id=conversation.id,
        content=content,
        mime_type="application/pdf",
        original_filename="pix-a.pdf",
    )

    message = Message(
        conversation_id=conversation.id,
        direction="INBOUND",
        sender_type="CUSTOMER",
        content_type="DOCUMENT",
        content="[Documento recebido: pix-a.pdf]",
        metadata_json={
            "media_id": "media-pix-a",
            "stored_media": True,
            "stored_media_path": stored.relative_path,
            "mime_type": stored.mime_type,
            "file_size": stored.file_size,
            "sha256": stored.sha256,
            "filename": "pix-a.pdf",
        },
    )
    db.add(message)
    db.commit()

    monkeypatch.setattr(
        operations_api,
        "ConversationMediaStorage",
        lambda: ConversationMediaStorage(
            root_path=media_root,
            max_bytes=1024 * 1024,
        ),
    )
    monkeypatch.setattr(
        settings,
        "payment_receipt_storage_path",
        str(receipt_root),
    )

    with pytest.raises(operations_api.HTTPException) as error:
        operations_api.confirm_human_pix(
            conversation_id=conversation.id,
            order_id=order.id,
            message_id=message.id,
            assigned_to="Atendente",
            _access=None,
            db=db,
        )

    assert error.value.status_code == 422
    assert "não pertence ao cliente" in str(error.value.detail)

    receipt = db.scalar(
        select(PaymentReceipt).where(
            PaymentReceipt.order_id == order.id
        )
    )
    assert receipt is None

def test_human_pix_confirmation_rejects_non_customer_media():
    db, store, _, conversation = setup_context()
    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    customer = Customer(
        store_id=store.id,
        name="Cliente PIX",
        phone="5597991112222",
    )
    db.add(customer)
    db.flush()
    conversation.customer_id = customer.id

    cart = Cart(
        store_id=store.id,
        customer_id=customer.id,
        status="CHECKED_OUT",
        service_mode="DELIVERY",
    )
    db.add(cart)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=cart.id,
        display_id="000905",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name=customer.name,
        customer_phone=customer.phone,
    )
    db.add(order)
    db.flush()

    message = Message(
        conversation_id=conversation.id,
        direction="OUTBOUND",
        sender_type="HUMAN",
        content_type="DOCUMENT",
        content="[Arquivo enviado: falso.pdf]",
        metadata_json={
            "stored_media": True,
            "stored_media_path": "falso.pdf",
            "mime_type": "application/pdf",
            "sha256": "a" * 64,
        },
    )
    db.add(message)
    db.commit()

    with pytest.raises(operations_api.HTTPException) as error:
        operations_api.confirm_human_pix(
            conversation_id=conversation.id,
            order_id=order.id,
            message_id=message.id,
            assigned_to="Atendente",
            _access=None,
            db=db,
        )

    assert error.value.status_code == 422
    assert "recebido do cliente" in str(error.value.detail)
    receipt = db.scalar(
        select(PaymentReceipt).where(
            PaymentReceipt.order_id == order.id
        )
    )
    assert receipt is None


def test_central_takeover_assigns_active_ticket():
    db, store, _, conversation = setup_context()
    service = ConversationService()

    ticket = service.create_ticket(
        db,
        store_id=store.id,
        payload=HumanTicketCreate(
            conversation_id=conversation.id,
            category="OTHER",
            priority="URGENT",
            reason="Atendimento humano",
            customer_message="Olá",
        ),
    )

    result = operations_api.take_over(
        conversation_id=conversation.id,
        payload=ConversationTakeoverRequest(
            assigned_to="Atendente Central",
        ),
        _access=None,
        db=db,
    )

    db.refresh(ticket)

    assert result["status"] == "HUMAN"
    assert ticket.status == "IN_PROGRESS"
    assert ticket.assigned_to == "Atendente Central"


def test_store_human_only_routes_inbound_without_olivia(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", False)
    db, store, account, conversation = setup_context()

    store.operation_mode = "HUMAN_ONLY"
    db.commit()

    repository = ChannelRepository()
    event = repository.create_event(
        db,
        account=account,
        external_event_id="wamid-store-human-only",
        event_type="INBOUND_MESSAGE",
        payload={
            "id": "wamid-store-human-only",
            "from": "5597991112222",
            "type": "text",
            "text": {"body": "Quero falar com atendente"},
        },
    )

    WhatsAppGatewayService(
        repository=repository,
        orchestrator_factory=lambda: FailingOrchestrator(),
    ).process_event(db, account, event)

    db.refresh(conversation)

    assert conversation.status == "WAITING_HUMAN"

    messages = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id
            )
        )
    )
    assert any(
        message.sender_type == "CUSTOMER"
        and message.content == "Quero falar com atendente"
        for message in messages
    )


def test_store_human_only_never_resumes_olivia_on_timeout(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", False)
    db, store, _, conversation = setup_context()

    store.operation_mode = "HUMAN_ONLY"
    conversation.status = "WAITING_HUMAN"

    wait_event = AIEvent(
        store_id=store.id,
        conversation_id=conversation.id,
        event_type="HUMAN_WAITING",
        success=True,
        payload_json={"reason": "modo humano da loja"},
    )
    db.add(wait_event)
    db.commit()
    db.refresh(wait_event)

    monitor = HumanHandoffMonitor(
        orchestrator_factory=lambda: FailingOrchestrator()
    )

    now = wait_event.created_at + timedelta(
        seconds=settings.human_wait_timeout_seconds + 60
    )

    result = monitor.run_once(
        db,
        now=now,
    )

    db.refresh(conversation)

    assert result.resumed == 0
    assert result.failed == 0
    assert conversation.status == "WAITING_HUMAN"

    timeout_event = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "HUMAN_WAIT_TIMEOUT",
        )
    )
    assert timeout_event is None

def test_resolve_active_order_reports_olivia_waiting():
    db, store, account, conversation = setup_context()
    service = ConversationService()

    customer = Customer(
        store_id=store.id,
        name="Cliente",
        phone="5597991112222",
    )
    db.add(customer)
    db.flush()
    conversation.customer_id = customer.id

    cart = Cart(
        store_id=store.id,
        customer_id=customer.id,
        status="CHECKED_OUT",
        service_mode="DELIVERY",
    )
    db.add(cart)
    db.flush()

    db.add(Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=cart.id,
        display_id="000991",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name=customer.name,
        customer_phone=customer.phone,
    ))

    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente Teste",
    )

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone="5597988877665",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        current_conversation_id=conversation.id,
    )
    db.add(staff)
    db.flush()

    ticket = service.create_ticket(
        db,
        store_id=store.id,
        payload=HumanTicketCreate(
            conversation_id=conversation.id,
            category="OTHER",
            priority="URGENT",
            reason="Pedido ativo",
            customer_message="Quero alterar o pedido",
        ),
    )
    service.assign_ticket(
        db,
        ticket_id=ticket.id,
        assigned_to="Atendente Teste",
    )
    db.commit()

    HumanRelayService()._resolve(
        db,
        account=account,
        staff=staff,
        resolution="Ajustado manualmente",
    )

    db.refresh(conversation)
    db.refresh(ticket)
    db.refresh(staff)

    assert ticket.status == "RESOLVED"
    assert conversation.status == "OPEN"
    assert staff.current_conversation_id is None

    outbound = db.scalar(
        select(OutboundChannelMessage)
        .where(OutboundChannelMessage.recipient == staff.phone)
        .order_by(OutboundChannelMessage.created_at.desc())
        .limit(1)
    )

    assert outbound is not None
    assert "permanecer\u00e1 em espera" in outbound.content
    assert "#000991" in outbound.content
    assert "continuar\u00e3o autom\u00e1ticas" in outbound.content


def test_release_resume_processes_pending_customer_message():
    from app.schemas.conversation import MessageCreate
    from app.services.olivia_release_resume import (
        OliviaReleaseResumeService,
    )

    db, _, _, conversation = setup_context()
    service = ConversationService()

    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    service.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="INBOUND",
            sender_type="CUSTOMER",
            content="Quero um x salada gourmet",
        ),
    )

    class ResumeOrchestrator:
        def __init__(self):
            self.calls = []

        def reply(self, db, **kwargs):
            self.calls.append(kwargs)

            ConversationService().add_message(
                db,
                conversation_id=kwargs[
                    "conversation_id"
                ],
                payload=MessageCreate(
                    direction="OUTBOUND",
                    sender_type="OLIVIA",
                    content=(
                        "Claro! Vamos continuar "
                        "seu pedido."
                    ),
                ),
            )

            return "Claro! Vamos continuar seu pedido."

    orchestrator = ResumeOrchestrator()

    released = service.release_to_olivia(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    resumed = OliviaReleaseResumeService(
        orchestrator_factory=lambda: orchestrator,
    ).resume_if_needed(
        db,
        conversation=released,
    )

    db.refresh(conversation)

    assert resumed is True
    assert conversation.status == "OPEN"
    assert len(orchestrator.calls) == 1
    assert (
        orchestrator.calls[0][
            "record_customer_message"
        ]
        is False
    )

    event = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id
            == conversation.id,
            AIEvent.event_type
            == "HUMAN_RELEASE_RESUMED",
        )
    )

    assert event is not None


def test_release_resume_does_not_call_openai_if_human_replied():
    from app.schemas.conversation import MessageCreate
    from app.services.olivia_release_resume import (
        OliviaReleaseResumeService,
    )

    db, _, _, conversation = setup_context()
    service = ConversationService()

    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    service.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="INBOUND",
            sender_type="CUSTOMER",
            content="Preciso de ajuda",
        ),
    )

    service.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="OUTBOUND",
            sender_type="HUMAN",
            content="Já resolvi para você.",
        ),
    )

    released = service.release_to_olivia(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    resumed = OliviaReleaseResumeService(
        orchestrator_factory=lambda: (
            FailingOrchestrator()
        ),
    ).resume_if_needed(
        db,
        conversation=released,
    )

    db.refresh(conversation)

    assert resumed is False
    assert conversation.status == "OPEN"


def test_release_resume_recovers_message_sent_while_waiting_human():
    from app.schemas.conversation import MessageCreate
    from app.services.olivia_release_resume import (
        OliviaReleaseResumeService,
    )

    db, _, _, conversation = setup_context()
    service = ConversationService()

    # Falha/encaminhamento para humano.
    service.wait_for_human(
        db,
        conversation_id=conversation.id,
        reason="OpenAI indisponível",
    )

    # Cliente escreve enquanto ainda aguarda alguém assumir.
    service.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="INBOUND",
            sender_type="CUSTOMER",
            content="Quero fazer um novo pedido",
        ),
    )

    # Atendente assume, mas não responde.
    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    class ResumeOrchestrator:
        def __init__(self):
            self.calls = []

        def reply(self, db, **kwargs):
            self.calls.append(kwargs)

            ConversationService().add_message(
                db,
                conversation_id=kwargs[
                    "conversation_id"
                ],
                payload=MessageCreate(
                    direction="OUTBOUND",
                    sender_type="OLIVIA",
                    content="Vamos continuar seu pedido.",
                ),
            )

            return "Vamos continuar seu pedido."

    orchestrator = ResumeOrchestrator()

    released = service.release_to_olivia(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    resumed = OliviaReleaseResumeService(
        orchestrator_factory=lambda: orchestrator,
    ).resume_if_needed(
        db,
        conversation=released,
    )

    db.refresh(conversation)

    assert resumed is True
    assert conversation.status == "OPEN"
    assert len(orchestrator.calls) == 1
    assert (
        orchestrator.calls[0]["record_customer_message"]
        is False
    )


def test_release_resume_does_not_revive_old_pre_takeover_message():
    from app.schemas.conversation import MessageCreate
    from app.services.olivia_release_resume import (
        OliviaReleaseResumeService,
    )

    db, _, _, conversation = setup_context()
    service = ConversationService()

    # Mensagem antiga, antes do ciclo humano começar.
    service.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="INBOUND",
            sender_type="CUSTOMER",
            content="Mensagem antiga sem resposta",
        ),
    )

    # Tomada manual/proativa posterior.
    service.take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    released = service.release_to_olivia(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente",
    )

    resumed = OliviaReleaseResumeService(
        orchestrator_factory=lambda: (
            FailingOrchestrator()
        ),
    ).resume_if_needed(
        db,
        conversation=released,
    )

    db.refresh(conversation)

    assert resumed is False
    assert conversation.status == "OPEN"
