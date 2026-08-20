from decimal import Decimal
from uuid import uuid4

import hashlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.providers.openai_provider import OpenAIProviderRequestError
from app.channels.whatsapp.client import DownloadedMedia
from app.channels.whatsapp.security import hash_verify_token, verify_meta_signature
from app.channels.whatsapp.service import WhatsAppGatewayService
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage
from app.models.conversation import AIEvent, Conversation, Message, HumanTicket
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.models.staff import StoreStaffMember
from app.services.pix_receipt import PixReceiptService
from app.services.human_relay import HumanRelayService


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def reply(self, db, **kwargs):
        self.calls.append(kwargs)
        # The real orchestrator persists inbound/outbound messages. Simulate that contract.
        from app.schemas.conversation import MessageCreate
        from app.services.conversation import ConversationService

        service = ConversationService()
        service.add_message(
            db,
            conversation_id=kwargs["conversation_id"],
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content=kwargs["customer_message"],
            ),
        )
        service.add_message(
            db,
            conversation_id=kwargs["conversation_id"],
            payload=MessageCreate(
                direction="OUTBOUND",
                sender_type="OLIVIA",
                content="Olá! Como posso ajudar?",
            ),
        )
        return "Olá! Como posso ajudar?"


class FakeClient:
    def __init__(self):
        self.sent = []
        self.media_sent = []

    def send_text(self, **kwargs):
        self.sent.append(kwargs)
        return "wamid.outbound-1"

    def send_media_by_id(self, **kwargs):
        self.media_sent.append(kwargs)
        return "wamid.media-outbound-1"

    def download_media(self, **kwargs):
        content = b"imagem-teste-whatsapp"
        return DownloadedMedia(
            content=content,
            mime_type="image/png",
            meta_sha256=None,
            file_size=len(content),
        )


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
    account = ChannelAccount(
        store_id=store.id,
        provider="WHATSAPP_CLOUD",
        external_account_id="phone-number-id-1",
        display_phone_number="5597999999999",
        verify_token_hash=hash_verify_token("verify-token-123456"),
        active=True,
    )
    db.add(account)
    db.commit()
    return db, store, account


def inbound_payload(message_id="wamid.inbound-1", message_type="text"):
    message = {
        "from": "5597999999999",
        "id": message_id,
        "timestamp": "1785942000",
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = {"body": "Oi"}
    else:
        message[message_type] = {"id": "media-1"}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5597999999999",
                                "phone_number_id": "phone-number-id-1",
                            },
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def test_inbound_text_creates_conversation_and_sends_reply():
    db, store, account = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    result = service.process_payload(db, inbound_payload())

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0
    conversation = db.scalar(select(Conversation))
    assert conversation.store_id == store.id
    assert conversation.external_conversation_id == "5597999999999"
    assert len(list(db.scalars(select(Message)))) == 2
    outbound = db.scalar(select(OutboundChannelMessage))
    assert outbound.status == "SENT_TO_META"
    assert outbound.external_message_id == "wamid.outbound-1"
    assert client.sent[0]["phone_number_id"] == account.external_account_id


def test_duplicate_webhook_does_not_reply_twice():
    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )
    payload = inbound_payload()

    first = service.process_payload(db, payload)
    second = service.process_payload(db, payload)

    assert first.processed == 1
    assert second.duplicated == 1
    assert len(client.sent) == 1
    assert len(list(db.scalars(select(ChannelEvent)))) == 1


def test_image_without_recent_pix_order_is_processed():
    db, _, _ = setup_db()
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        inbound_payload(message_type="image"),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.ignored == 0
    assert result.failed == 0

    event = db.scalar(select(ChannelEvent))
    assert event.status == "PROCESSED"
    assert event.error_message is None

    messages = list(
        db.scalars(select(Message))
    )
    assert len(messages) == 1
    assert messages[0].content == (
        "[Imagem/arquivo recebido]"
    )

    outbound = db.scalar(
        select(OutboundChannelMessage)
    )
    assert outbound is not None
    assert "pedido PIX recente" not in outbound.content
    assert "comprovante de PIX" not in outbound.content
    assert "atendimento humano" in outbound.content
    assert outbound.status == "SENT_TO_META"


def test_signature_validation_uses_meta_hmac_format():
    import hashlib
    import hmac

    body = b'{"object":"whatsapp_business_account"}'
    secret = "app-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_meta_signature(body, f"sha256={digest}", secret) is True
    assert verify_meta_signature(body, "sha256=wrong", secret) is False



def test_exact_duplicate_pix_receipt_does_not_create_new_receipt():
    db, store, account = setup_db()

    sender = "5597988887777"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=sender,
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    content = b"comprovante-pix-exatamente-igual"
    digest = hashlib.sha256(content).hexdigest()

    previous = PaymentReceipt(
        store_id=store.id,
        conversation_id=conversation.id,
        external_media_id="media-original",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256=digest,
        status="AUTO_CONFIRMED",
    )
    db.add(previous)
    db.flush()

    event = ChannelEvent(
        channel_account_id=account.id,
        provider="WHATSAPP_CLOUD",
        external_event_id="wamid-duplicate-file",
        event_type="INBOUND_MESSAGE",
        payload_json={},
    )
    db.add(event)
    db.commit()

    class DuplicateMediaClient:
        def download_media(self, **kwargs):
            return DownloadedMedia(
                content=content,
                mime_type="image/png",
                meta_sha256=None,
                file_size=len(content),
            )

    service = PixReceiptService()

    result = service.receive_whatsapp_media(
        db,
        account=account,
        event=event,
        conversation=conversation,
        sender=sender,
        message={
            "type": "image",
            "image": {
                "id": "media-duplicate",
                "mime_type": "image/png",
            },
        },
        client=DuplicateMediaClient(),
        allow_customer_reply=False,
    )

    receipts = list(
        db.scalars(
            select(PaymentReceipt).where(
                PaymentReceipt.store_id == store.id
            )
        )
    )

    assert result is None
    assert len(receipts) == 1
    assert receipts[0].id == previous.id
    assert receipts[0].file_sha256 == digest

    messages = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id
            )
        )
    )

    assert len(messages) == 1
    assert messages[0].content_type == "IMAGE"
    assert messages[0].content == "[Comprovante PIX recebido]"
    assert messages[0].metadata_json["payment_receipt_id"] == str(
        previous.id
    )


def test_rejected_duplicate_pix_asks_for_new_transaction():
    db, store, account = setup_db()

    sender = "5597988887777"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=sender,
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
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("20.00"),
        customer_name="Cliente Teste",
        customer_phone=sender,
    )
    db.add(order)
    db.flush()

    content = b"comprovante-rejeitado-identico"
    digest = hashlib.sha256(content).hexdigest()

    previous = PaymentReceipt(
        store_id=store.id,
        order_id=order.id,
        conversation_id=conversation.id,
        external_media_id="media-rejeitada-original",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256=digest,
        status="HUMAN_REJECTED",
    )
    db.add(previous)
    db.flush()

    event = ChannelEvent(
        channel_account_id=account.id,
        provider="WHATSAPP_CLOUD",
        external_event_id="wamid-rejected-duplicate",
        event_type="INBOUND_MESSAGE",
        payload_json={},
    )
    db.add(event)
    db.commit()

    class DuplicateRejectedMediaClient:
        def download_media(self, **kwargs):
            return DownloadedMedia(
                content=content,
                mime_type="image/png",
                meta_sha256=None,
                file_size=len(content),
            )

    result = PixReceiptService().receive_whatsapp_media(
        db,
        account=account,
        event=event,
        conversation=conversation,
        sender=sender,
        message={
            "type": "image",
            "image": {
                "id": "media-rejeitada-reenviada",
                "mime_type": "image/png",
            },
        },
        client=DuplicateRejectedMediaClient(),
        allow_customer_reply=True,
    )

    receipts = list(
        db.scalars(
            select(PaymentReceipt).where(
                PaymentReceipt.store_id == store.id
            )
        )
    )

    outbound = list(
        db.scalars(
            select(OutboundChannelMessage).where(
                OutboundChannelMessage.recipient == sender
            )
        )
    )

    assert result is None
    assert len(receipts) == 1
    assert receipts[0].id == previous.id
    assert receipts[0].status == "HUMAN_REJECTED"

    assert len(outbound) == 1
    assert "mesmo comprovante" in outbound[0].content
    assert "já foi recusado" in outbound[0].content
    assert "nova transação PIX" in outbound[0].content
    assert "registrado para conferência" not in outbound[0].content


def test_human_image_is_forwarded_to_staff_without_pix_receipt():
    db, store, _ = setup_db()

    customer_phone = "5597999999999"
    staff_phone = "5597988887777"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="HUMAN",
    )
    db.add(conversation)
    db.flush()

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone=staff_phone,
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        current_conversation_id=conversation.id,
    )
    db.add(staff)
    db.commit()

    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: client,
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.human-image-1",
            message_type="image",
        ),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    receipts = list(
        db.scalars(select(PaymentReceipt))
    )

    assert receipts == []

    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
        )
    )

    assert len(messages) == 1
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[0].content_type == "IMAGE"
    assert messages[0].content == "[Imagem recebida]"
    assert messages[0].metadata_json["media_id"] == "media-1"
    assert messages[0].metadata_json["media_type"] == "image"

    outbound = db.scalar(
        select(OutboundChannelMessage)
        .where(
            OutboundChannelMessage.recipient == staff_phone
        )
    )

    assert outbound is not None
    assert outbound.content_type == "MEDIA_ID"
    assert outbound.status == "SENT_TO_META"
    assert outbound.external_message_id == "wamid.media-outbound-1"

    assert len(client.media_sent) == 1

    sent = client.media_sent[0]

    assert sent["recipient"] == staff_phone
    assert sent["media_id"] == "media-1"
    assert sent["media_type"] == "image"
    assert "Cliente" in sent["caption"]



def test_human_location_is_forwarded_to_staff_without_pix_flow():
    db, store, _ = setup_db()

    customer_phone = "5597999999999"
    staff_phone = "5597988887777"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="HUMAN",
    )
    db.add(conversation)
    db.flush()

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone=staff_phone,
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        current_conversation_id=conversation.id,
    )
    db.add(staff)
    db.commit()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5597999999999",
                                "phone_number_id": "phone-number-id-1",
                            },
                            "messages": [
                                {
                                    "from": customer_phone,
                                    "id": "wamid.human-location-1",
                                    "timestamp": "1785942000",
                                    "type": "location",
                                    "location": {
                                        "latitude": -4.0944,
                                        "longitude": -63.1411,
                                        "name": "Local do cliente",
                                        "address": "Coari - AM",
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    result = service.process_payload(db, payload)

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    assert orchestrator.calls == []

    assert list(db.scalars(select(PaymentReceipt))) == []

    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
        )
    )

    assert len(messages) == 1
    assert messages[0].sender_type == "CUSTOMER"
    assert "Localização compartilhada" in messages[0].content
    assert "-4.0944" in messages[0].content
    assert "-63.1411" in messages[0].content
    assert "google.com/maps" in messages[0].content

    outbound = db.scalar(
        select(OutboundChannelMessage)
        .where(
            OutboundChannelMessage.recipient == staff_phone
        )
    )

    assert outbound is not None
    assert outbound.content_type == "TEXT"
    assert outbound.status == "SENT_TO_META"
    assert "Localização compartilhada" in outbound.content
    assert "-4.0944" in outbound.content
    assert "-63.1411" in outbound.content
    assert "google.com/maps" in outbound.content

    assert len(client.sent) == 1
    assert client.sent[0]["recipient"] == staff_phone



def test_localizar_pedido_assumes_delivery_and_asks_for_location():
    db, store, account = setup_db()

    customer_phone = "5597977776666"
    staff_phone = "5597988887777"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone=staff_phone,
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
    )
    db.add(staff)

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000123",
        status="DISPATCHED",
        service_mode="DELIVERY",
        payment_method="CASH",
        payment_type="OFFLINE",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name="Cliente Localização",
        customer_phone=customer_phone,
        address_street="Rua Teste",
        address_number="123",
        address_neighborhood="Centro",
        address_city="Coari",
        address_state="AM",
        address_reference="Próximo à praça",
    )
    db.add(order)
    db.commit()

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=staff,
        body="LOCALIZAR PEDIDO 123",
    )

    db.refresh(conversation)
    db.refresh(staff)

    assert conversation.status == "HUMAN"
    assert staff.current_conversation_id == conversation.id

    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    )

    assert len(messages) == 1
    assert messages[0].sender_type == "HUMAN"
    assert "pedido #000123" in messages[0].content
    assert "localização pelo WhatsApp" in messages[0].content
    assert "foto da fachada/rua" in messages[0].content
    assert "ponto de referência" in messages[0].content

    outbounds = list(
        db.scalars(
            select(OutboundChannelMessage)
            .order_by(OutboundChannelMessage.created_at)
        )
    )

    customer_outbound = [
        item
        for item in outbounds
        if item.recipient == customer_phone
    ]

    staff_outbound = [
        item
        for item in outbounds
        if item.recipient == staff_phone
    ]

    assert len(customer_outbound) == 1
    assert "dificuldade para localizar" in customer_outbound[0].content
    assert "localização pelo WhatsApp" in customer_outbound[0].content

    assert len(staff_outbound) == 1
    assert "Localização iniciada" in staff_outbound[0].content
    assert "#000123" in staff_outbound[0].content
    assert "Rua Teste, 123" in staff_outbound[0].content
    assert "Centro" in staff_outbound[0].content
    assert "Próximo à praça" in staff_outbound[0].content
    assert "assumida por você imediatamente" in staff_outbound[0].content




def test_localizar_pedido_rejects_unknown_order():
    db, store, account = setup_db()

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone="5597988887777",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
    )
    db.add(staff)
    db.commit()

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=staff,
        body="LOCALIZAR PEDIDO 999999",
    )

    db.refresh(staff)

    assert staff.current_conversation_id is None

    outbound = db.scalar(
        select(OutboundChannelMessage)
        .where(
            OutboundChannelMessage.recipient == staff.phone
        )
    )

    assert outbound is not None
    assert "Não encontrei o pedido #999999" in outbound.content


def test_localizar_pedido_rejects_non_delivery_order():
    db, store, account = setup_db()

    customer_phone = "5597977776666"

    staff = StoreStaffMember(
        store_id=store.id,
        name="Atendente Teste",
        phone="5597988887777",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
    )
    db.add(staff)

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000124",
        status="READY",
        service_mode="TAKEOUT",
        payment_method="CASH",
        payment_type="OFFLINE",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("20.00"),
        customer_name="Cliente Retirada",
        customer_phone=customer_phone,
    )
    db.add(order)
    db.commit()

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=staff,
        body="LOCALIZAR PEDIDO 124",
    )

    db.refresh(staff)

    assert staff.current_conversation_id is None

    outbound = db.scalar(
        select(OutboundChannelMessage)
        .where(
            OutboundChannelMessage.recipient == staff.phone
        )
    )

    assert outbound is not None
    assert "#000124" in outbound.content
    assert "não é DELIVERY" in outbound.content


def test_localizar_pedido_does_not_steal_other_staff_conversation():
    db, store, account = setup_db()

    customer_phone = "5597977776666"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="HUMAN",
    )
    db.add(conversation)
    db.flush()

    owner = StoreStaffMember(
        store_id=store.id,
        name="Atendente A",
        phone="5597988881111",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
        current_conversation_id=conversation.id,
    )
    db.add(owner)

    requester = StoreStaffMember(
        store_id=store.id,
        name="Atendente B",
        phone="5597988882222",
        role="ATTENDANT",
        active=True,
        notify_whatsapp=True,
    )
    db.add(requester)

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000125",
        status="DISPATCHED",
        service_mode="DELIVERY",
        payment_method="CASH",
        payment_type="OFFLINE",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name="Cliente Já Atendido",
        customer_phone=customer_phone,
    )
    db.add(order)
    db.commit()

    HumanRelayService().handle_staff_message(
        db,
        account=account,
        staff=requester,
        body="LOCALIZAR PEDIDO 125",
    )

    db.refresh(conversation)
    db.refresh(owner)
    db.refresh(requester)

    assert conversation.status == "HUMAN"
    assert owner.current_conversation_id == conversation.id
    assert requester.current_conversation_id is None

    requester_message = db.scalar(
        select(OutboundChannelMessage)
        .where(
            OutboundChannelMessage.recipient == requester.phone
        )
    )

    assert requester_message is not None
    assert "já está sendo atendido por Atendente A" in (
        requester_message.content
    )

    customer_messages = list(
        db.scalars(
            select(OutboundChannelMessage)
            .where(
                OutboundChannelMessage.recipient == customer_phone
            )
        )
    )

    assert customer_messages == []


def test_human_media_without_linked_staff_fails_safely():
    db, store, _ = setup_db()

    customer_phone = "5597999999999"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="HUMAN",
    )
    db.add(conversation)
    db.commit()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.human-image-no-staff",
            message_type="image",
        ),
    )

    assert result.received == 1
    assert result.processed == 0
    assert result.failed == 1

    assert list(db.scalars(select(PaymentReceipt))) == []

    assert list(
        db.scalars(
            select(OutboundChannelMessage)
        )
    ) == []

    event = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.external_event_id
            == "wamid.human-image-no-staff"
        )
    )

    assert event is not None
    assert event.status == "FAILED"
    assert "HUMAN sem atendente vinculado" in (
        event.error_message or ""
    )


def test_human_media_without_linked_staff_fails_safely():
    db, store, _ = setup_db()

    customer_phone = "5597999999999"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=customer_phone,
        status="HUMAN",
    )
    db.add(conversation)
    db.commit()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.human-image-no-staff",
            message_type="image",
        ),
    )

    assert result.received == 1
    assert result.processed == 0
    assert result.failed == 1

    assert list(db.scalars(select(PaymentReceipt))) == []

    assert list(
        db.scalars(
            select(OutboundChannelMessage)
        )
    ) == []

    event = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.external_event_id
            == "wamid.human-image-no-staff"
        )
    )

    assert event is not None
    assert event.status == "FAILED"
    assert "HUMAN sem atendente vinculado" in (
        event.error_message or ""
    )


def test_open_location_is_not_sent_to_olivia():
    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5597999999999",
                                "phone_number_id": "phone-number-id-1",
                            },
                            "messages": [
                                {
                                    "from": "5597999999999",
                                    "id": "wamid.open-location-1",
                                    "timestamp": "1785942000",
                                    "type": "location",
                                    "location": {
                                        "latitude": -4.0944,
                                        "longitude": -63.1411,
                                        "name": "Local do cliente",
                                        "address": "Coari - AM",
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    result = service.process_payload(db, payload)

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    # A localização nunca chega à Olívia.
    assert orchestrator.calls == []

    # Localização em conversa OPEN não vira comprovante PIX.
    assert list(db.scalars(select(PaymentReceipt))) == []

    # Latitude, longitude e mapa não entram no histórico da Olívia.
    messages = list(db.scalars(select(Message)))
    assert messages == []

    outbound = db.scalar(select(OutboundChannelMessage))
    assert outbound is not None
    assert "endereço em texto" in outbound.content
    assert "ponto de referência" in outbound.content
    assert "Latitude" not in outbound.content
    assert "google.com/maps" not in outbound.content


def test_recent_pix_order_without_conversation_checkout_does_not_treat_image_as_receipt():
    db, store, _ = setup_db()

    sender = "5597999999999"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=sender,
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000888",
        status="READY_FOR_INTEGRATION",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("25.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("25.00"),
        customer_name="Cliente Teste",
        customer_phone=sender,
    )
    db.add(order)
    db.commit()

    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.foto-comum-com-pix-recente",
            message_type="image",
        ),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    # A foto comum não deve virar comprovante apenas porque existe
    # um pedido PIX recente desse telefone.
    assert list(db.scalars(select(PaymentReceipt))) == []

    # Imagem também não deve ser enviada à Olívia.
    assert orchestrator.calls == []

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.recipient == sender
        )
    )
    assert outbound is not None

    # Sem contexto explícito de checkout PIX, a resposta não deve
    # induzir o cliente a acreditar que a imagem foi tratada como PIX.
    assert "pedido PIX recente" not in outbound.content
    assert "comprovante de PIX" not in outbound.content



def test_pix_checkout_in_same_conversation_enables_receipt_candidate():
    db, store, _ = setup_db()

    sender = "5597999999999"

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id=sender,
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000889",
        status="READY_FOR_INTEGRATION",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("25.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("25.00"),
        customer_name="Cliente Teste",
        customer_phone=sender,
    )
    db.add(order)
    db.flush()

    checkout_event = AIEvent(
        store_id=store.id,
        conversation_id=conversation.id,
        event_type="TOOL_EXECUTION",
        tool_name="checkout_cart",
        success=True,
        payload_json={
            "arguments": {},
            "result": {
                "ok": True,
                "data": {
                    "id": str(order.id),
                    "display_id": order.display_id,
                    "payment_method": "PIX",
                    "total": 25.00,
                },
                "error": None,
                "requires_human": False,
            },
        },
    )
    db.add(checkout_event)
    db.commit()

    candidates = PixReceiptService()._recent_pix_orders(
        db,
        store_id=store.id,
        customer_phone=sender,
        conversation_id=conversation.id,
    )

    assert len(candidates) == 1
    assert candidates[0].id == order.id
    assert candidates[0].payment_method == "PIX"



class OpenAIFailingOrchestrator:
    def reply(self, db, **kwargs):
        from app.schemas.conversation import MessageCreate
        from app.services.conversation import ConversationService

        ConversationService().add_message(
            db,
            conversation_id=kwargs["conversation_id"],
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content=kwargs["customer_message"],
            ),
        )

        raise OpenAIProviderRequestError(
            "OpenAI: insufficient_quota"
        )


def test_openai_failure_returns_fallback_and_handoff():
    db, _, _ = setup_db()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: OpenAIFailingOrchestrator(),
        client_factory=lambda: client,
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.openai-outage",
        ),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    conversation = db.scalar(select(Conversation))

    assert conversation.status == "WAITING_HUMAN"

    failure = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "AI_PROVIDER_FAILURE",
        )
    )

    assert failure is not None
    assert failure.success is False

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id == conversation.id
            )
        )
    )

    assert len(tickets) == 1
    assert tickets[0].priority == "URGENT"

    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.conversation_id
            == conversation.id
        )
    )

    assert outbound is not None
    assert "instabilidade temporária" in outbound.content
    assert "Não precisa repetir" in outbound.content
