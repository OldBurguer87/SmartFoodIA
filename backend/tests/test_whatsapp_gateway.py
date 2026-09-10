from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import hashlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.olivia_prompt import OLIVIA_INSTRUCTIONS
from app.ai.providers.openai_provider import OpenAIProviderRequestError
from app.channels.whatsapp.client import DownloadedMedia
from app.channels.whatsapp.security import hash_verify_token, verify_meta_signature
from app.channels.whatsapp.service import WhatsAppGatewayService
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage
from app.models.conversation import AIEvent, Conversation, Message, HumanTicket
from app.models.commercial import StoreCommercialRules
from app.models.catalog_version import CatalogVersion
from app.models.menu import StoreMenuDocument
from app.models.customer import Customer
from app.models.order import Order, OrderPayment
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


def test_image_without_recent_pix_order_is_processed(tmp_path):
    from app.services.conversation_media import ConversationMediaStorage

    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
        conversation_media_storage=ConversationMediaStorage(
            root_path=tmp_path,
        ),
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

    metadata = messages[0].metadata_json or {}

    assert metadata["stored_media"] is True
    assert metadata["mime_type"] == "image/png"

    stored_path = (
        tmp_path
        / metadata["stored_media_path"]
    )

    assert stored_path.is_file()
    assert stored_path.read_bytes() == b"imagem-teste-whatsapp"

    # Armazenar/visualizar imagem comum não chama a Olívia.
    assert orchestrator.calls == []

    outbound = db.scalar(
        select(OutboundChannelMessage)
    )
    assert outbound is not None
    assert "pedido PIX recente" not in outbound.content
    assert "comprovante de PIX" not in outbound.content
    assert "atendimento humano" in outbound.content
    assert outbound.status == "SENT_TO_META"


def test_non_pdf_document_is_stored_for_central_without_gpt(tmp_path):
    from app.services.conversation_media import ConversationMediaStorage

    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()

    class DocumentClient(FakeClient):
        def download_media(self, **kwargs):
            content = b"documento-teste-central"
            return DownloadedMedia(
                content=content,
                mime_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                meta_sha256=None,
                file_size=len(content),
            )

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: DocumentClient(),
        conversation_media_storage=ConversationMediaStorage(
            root_path=tmp_path,
        ),
    )

    payload = inbound_payload(
        message_id="wamid.document-central-1",
        message_type="document",
    )

    document = (
        payload["entry"][0]["changes"][0]["value"]
        ["messages"][0]["document"]
    )
    document["filename"] = "arquivo.docx"
    document["mime_type"] = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    )

    result = service.process_payload(db, payload)

    assert result.processed == 1
    assert result.failed == 0

    messages = list(db.scalars(select(Message)))
    assert len(messages) == 1

    message = messages[0]
    metadata = message.metadata_json or {}

    assert message.content_type == "DOCUMENT"
    assert metadata["stored_media"] is True
    assert metadata["filename"] == "arquivo.docx"

    stored_path = tmp_path / metadata["stored_media_path"]

    assert stored_path.is_file()
    assert stored_path.read_bytes() == b"documento-teste-central"

    assert list(db.scalars(select(PaymentReceipt))) == []
    assert orchestrator.calls == []


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


def test_human_image_is_forwarded_to_staff_without_pix_receipt(tmp_path):
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

    from app.services.conversation_media import (
        ConversationMediaStorage,
    )

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: client,
        conversation_media_storage=ConversationMediaStorage(
            root_path=tmp_path,
        ),
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
    assert messages[0].metadata_json["stored_media"] is True
    assert messages[0].metadata_json["mime_type"] == "image/png"

    stored_path = (
        tmp_path
        / messages[0].metadata_json["stored_media_path"]
    )

    assert stored_path.read_bytes() == b"imagem-teste-whatsapp"

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


def test_human_media_without_linked_staff_is_saved_for_web_central(tmp_path):
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

    from app.services.conversation_media import (
        ConversationMediaStorage,
    )

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
        conversation_media_storage=ConversationMediaStorage(
            root_path=tmp_path,
        ),
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.human-image-no-staff",
            message_type="image",
        ),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    assert list(db.scalars(select(PaymentReceipt))) == []

    assert list(
        db.scalars(select(OutboundChannelMessage))
    ) == []

    event = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.external_event_id
            == "wamid.human-image-no-staff"
        )
    )

    assert event is not None
    assert event.status == "PROCESSED"
    assert event.error_message is None

    messages = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id
            )
        )
    )

    assert len(messages) == 1
    assert messages[0].direction == "INBOUND"
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[0].content_type == "IMAGE"
    assert messages[0].metadata_json["stored_media"] is True
    assert messages[0].metadata_json["mime_type"] == "image/png"

    stored_path = (
        tmp_path
        / messages[0].metadata_json["stored_media_path"]
    )

    assert stored_path.read_bytes() == b"imagem-teste-whatsapp"


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

    # A localização nunca chega à Olívia/OpenAI.
    assert orchestrator.calls == []

    # Localização não vira comprovante PIX.
    assert list(db.scalars(select(PaymentReceipt))) == []

    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.status == "WAITING_HUMAN"

    # A localização fica disponível para o atendimento humano.
    messages = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id
            )
        )
    )
    assert len(messages) == 1
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[0].content_type == "LOCATION"
    assert "Localização compartilhada" in messages[0].content
    assert "-4.0944" in messages[0].content
    assert "-63.1411" in messages[0].content
    assert "google.com/maps" in messages[0].content

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id == conversation.id
            )
        )
    )
    assert len(tickets) == 1
    assert tickets[0].priority == "URGENT"
    assert tickets[0].reason == "Localização compartilhada pelo cliente"

    # Cliente recebe apenas o aviso de encaminhamento ao humano.
    outbound = db.scalar(
        select(OutboundChannelMessage).where(
            OutboundChannelMessage.conversation_id == conversation.id
        )
    )
    assert outbound is not None
    assert "atendente" in outbound.content.lower()
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

def test_sanitize_whatsapp_text_removes_replacement_character():
    from app.channels.whatsapp.service import sanitize_whatsapp_text

    result = sanitize_whatsapp_text(
        "Mensagem com caractere corrompido: �"
    )

    assert "�" not in result


def test_human_only_mode_routes_text_without_olivia(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "human_only_mode", True)

    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    result = service.process_payload(
        db,
        inbound_payload(message_id="wamid.human-only-text"),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    conversation = db.scalar(select(Conversation))
    assert conversation.store_id == store.id
    assert conversation.status == "WAITING_HUMAN"

    # A prova principal: nenhuma chamada à Olívia/OpenAI.
    assert orchestrator.calls == []

    messages = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id
            )
        )
    )
    assert len(messages) == 1
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[0].content == "Oi"

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id == conversation.id
            )
        )
    )
    assert len(tickets) == 1
    assert tickets[0].priority == "URGENT"


def test_human_only_mode_image_skips_pix_and_olivia(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "human_only_mode", True)

    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    from app.services.conversation_media import (
        ConversationMediaStorage,
    )

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
        conversation_media_storage=ConversationMediaStorage(
            root_path=tmp_path,
        ),
    )

    result = service.process_payload(
        db,
        inbound_payload(
            message_id="wamid.human-only-image",
            message_type="image",
        ),
    )

    assert result.received == 1
    assert result.processed == 1
    assert result.failed == 0

    conversation = db.scalar(select(Conversation))
    assert conversation.status == "WAITING_HUMAN"

    # Não chama Olívia.
    assert orchestrator.calls == []

    # Não cria comprovante para análise PIX.
    receipts = list(db.scalars(select(PaymentReceipt)))
    assert receipts == []

    messages = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id
            )
        )
    )
    assert len(messages) == 1
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[0].content_type == "IMAGE"
    assert messages[0].metadata_json["media_id"] == "media-1"
    assert messages[0].metadata_json["stored_media"] is True
    assert messages[0].metadata_json["mime_type"] == "image/png"

    stored_path = (
        tmp_path
        / messages[0].metadata_json["stored_media_path"]
    )

    assert stored_path.read_bytes() == b"imagem-teste-whatsapp"

def test_inbound_profile_creates_and_links_customer():
    db, store, _ = setup_db()
    payload = inbound_payload(message_id="wamid.profile-1")
    payload["entry"][0]["changes"][0]["value"]["contacts"] = [
        {
            "wa_id": "5597999999999",
            "profile": {"name": "Maria Teste"},
        }
    ]
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )
    result = service.process_payload(db, payload)
    assert result.processed == 1
    assert result.failed == 0
    customer = db.scalar(select(Customer).where(Customer.store_id == store.id, Customer.phone == "5597999999999"))
    assert customer is not None
    assert customer.name == "Maria Teste"
    conversation = db.scalar(select(Conversation).where(Conversation.store_id == store.id))
    assert conversation is not None
    assert conversation.customer_id == customer.id


def test_active_order_after_checkout_routes_directly_to_human_without_olivia():
    db, store, _ = setup_db()

    sender = "5597999999999"
    customer = Customer(
        store_id=store.id,
        name="Cliente Pós Checkout",
        phone=sender,
        active=True,
    )
    db.add(customer)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=uuid4(),
        display_id="000990",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("35.00"),
        customer_name=customer.name,
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

    payload = inbound_payload(message_id="wamid.post-checkout-active-1")
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message["text"]["body"] = "coloca uma batata também"

    result = service.process_payload(db, payload)

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
            Conversation.customer_id == customer.id,
        )
    )
    ticket = db.scalar(
        select(HumanTicket).where(
            HumanTicket.conversation_id == conversation.id,
        )
    )

    assert result.processed == 1
    assert result.failed == 0
    assert orchestrator.calls == []
    assert conversation.status == "WAITING_HUMAN"
    assert ticket is not None
    assert ticket.priority == "URGENT"
    assert "Pedido #000990 ativo após checkout" in ticket.reason
    assert ticket.customer_message == "coloca uma batata também"


def test_explicit_new_order_bypasses_active_previous_order():
    db, store, _ = setup_db()

    sender = "5597999999999"
    customer = Customer(
        store_id=store.id,
        name="Cliente Novo Pedido",
        phone=sender,
        active=True,
    )
    db.add(customer)
    db.flush()

    previous_order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=uuid4(),
        display_id="000990",
        status="CONFIRMED",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("67.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("70.00"),
        customer_name=customer.name,
        customer_phone=sender,
    )
    db.add(previous_order)
    db.commit()

    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    first = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.new-order-after-checkout-1",
            "Quero adicionar outro pedido",
        ),
    )

    assert first.processed == 1
    assert first.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
            Conversation.customer_id == customer.id,
        )
    )

    assert conversation is not None
    assert conversation.status == "OPEN"

    first_state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert first_state is not None
    assert first_state.payload_json["state"] == "COLLECTING_ORDER"

    second = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.new-order-after-checkout-2",
            "Adicionar um x-salada e uma batata junto com esse outro pedido",
        ),
    )

    assert second.processed == 1
    assert second.failed == 0
    assert orchestrator.calls == []

    db.refresh(conversation)

    assert conversation.status == "OPEN"

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id == conversation.id
            )
        )
    )

    assert tickets == []

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "INBOUND",
            )
            .order_by(Message.created_at)
        )
    )

    contents = [message.content for message in messages]

    assert "Quero adicionar outro pedido" in contents
    assert (
        "Adicionar um x-salada e uma batata junto com esse outro pedido"
        in contents
    )

    final_state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert final_state is not None
    assert final_state.payload_json["state"] == "COLLECTING_ORDER"

    db.close()


def test_terminal_order_after_checkout_does_not_block_olivia():
    for index, terminal_status in enumerate(("CONCLUDED", "CANCELLED"), start=1):
        db, store, _ = setup_db()

        sender = "5597999999999"
        customer = Customer(
            store_id=store.id,
            name="Cliente Pedido Finalizado",
            phone=sender,
            active=True,
        )
        db.add(customer)
        db.flush()

        order = Order(
            store_id=store.id,
            customer_id=customer.id,
            cart_id=uuid4(),
            display_id=f"00099{index}",
            status=terminal_status,
            service_mode="DELIVERY",
            payment_method="PIX",
            payment_type="PREPAID",
            subtotal=Decimal("30.00"),
            delivery_fee=Decimal("5.00"),
            discount=Decimal("0.00"),
            total=Decimal("35.00"),
            customer_name=customer.name,
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

        payload = inbound_payload(
            message_id=f"wamid.post-checkout-terminal-{index}"
        )
        message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        message["text"]["body"] = "quero fazer outro pedido"

        result = service.process_payload(db, payload)

        conversation = db.scalar(
            select(Conversation).where(
                Conversation.store_id == store.id,
                Conversation.customer_id == customer.id,
            )
        )

        assert result.processed == 1
        assert result.failed == 0
        assert orchestrator.calls == []
        assert conversation.status == "OPEN"

        db.close()


# ORDER COLLECTION COST OPTIMIZATION

def _order_collection_payload(message_id, body):
    payload = inbound_payload(message_id=message_id)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message["text"]["body"] = body
    return payload


def test_order_collection_zero_gpt_until_customer_ready_to_mount():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    # Primeira mensagem inicia a coleta sem GPT.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-1",
            "quero 2 x salada",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    # Outro item continua sem GPT.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-2",
            "e uma batata",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    # O cliente não fica mais em silêncio.
    acknowledgements = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "OUTBOUND",
                Message.sender_type == "OLIVIA",
            )
            .order_by(Message.created_at)
        )
    )

    assert any(
        "mais alguma coisa" in message.content.lower()
        and "montar seu pedido" in message.content.lower()
        for message in acknowledgements
    )

    # Ao dizer que terminou, libera exatamente UMA chamada da Olivia.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-3",
            "Somente isso",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1

    assert orchestrator.calls[0]["customer_message"] == "Somente isso"
    assert orchestrator.calls[0]["extra_instructions"] is None
    assert orchestrator.calls[0]["excluded_tools"] is None

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "NORMAL"
    assert state.payload_json["reason"] == "customer_ready_to_mount"

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "INBOUND",
            )
            .order_by(Message.created_at)
        )
    )

    contents = [message.content for message in messages]

    assert "quero 2 x salada" in contents
    assert "e uma batata" in contents
    assert "Somente isso" in contents

    db.close()


def test_order_collection_question_uses_olivia_once_and_keeps_collecting():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    # Inicia coleta sem GPT.
    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-question-1",
            "quero 2 x salada",
        ),
    )
    assert orchestrator.calls == []

    # Pergunta no meio do pedido precisa da Olivia.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-question-2",
            "tem coca 1 litro?",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1
    assert (
        orchestrator.calls[0]["customer_message"]
        == "tem coca 1 litro?"
    )

    assert (
        "COLETA DE PEDIDO"
        in orchestrator.calls[0]["extra_instructions"]
    )

    blocked = orchestrator.calls[0]["excluded_tools"]

    assert "add_cart_item" in blocked
    assert "update_cart_item" in blocked
    assert "remove_cart_item" in blocked
    assert "checkout_cart" in blocked

    assert "search_catalog" not in blocked
    assert "get_product" not in blocked

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    # A pergunta foi respondida, mas a coleta continua.
    assert state.payload_json["state"] == "COLLECTING_ORDER"

    # Próximo item volta a ser coletado sem nova chamada GPT.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-question-3",
            "então coloca uma coca 1 litro",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "INBOUND",
            )
            .order_by(Message.created_at)
        )
    )
    contents = [message.content for message in messages]

    assert "quero 2 x salada" in contents
    assert "tem coca 1 litro?" in contents
    assert "então coloca uma coca 1 litro" in contents

    db.close()


def test_order_collection_human_request_during_collection_uses_zero_gpt():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-human-1",
            "quero 2 x salada",
        ),
    )

    assert orchestrator.calls == []

    # Pedido de atendente durante COLLECTING_ORDER continua sem GPT.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-human-2",
            "quero falar com atendente",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    assert conversation.status == "WAITING_HUMAN"

    ticket = db.scalar(
        select(HumanTicket).where(
            HumanTicket.conversation_id == conversation.id,
        )
    )

    assert ticket is not None
    assert "coleta do pedido" in ticket.reason.lower()

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "NORMAL"
    assert state.payload_json["reason"] == "human_request"

    db.close()


def test_order_collection_same_message_order_and_finish_uses_zero_gpt():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-same-finish-1",
            "quero 2 x salada, só isso",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state is not None
    assert state.payload_json["state"] == "AWAITING_EXTRA"

    db.close()


def test_order_collection_information_request_does_not_start_collection():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-info-1",
            "quero saber o preço do x salada",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1
    assert (
        orchestrator.calls[0]["customer_message"]
        == "quero saber o preço do x salada"
    )
    assert orchestrator.calls[0]["extra_instructions"] is None
    assert orchestrator.calls[0]["excluded_tools"] is None

    db.close()


def test_order_collection_complaint_does_not_start_collection():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-complaint-1",
            "quero reclamar do atendimento",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1
    assert (
        orchestrator.calls[0]["customer_message"]
        == "quero reclamar do atendimento"
    )
    assert orchestrator.calls[0]["extra_instructions"] is None
    assert orchestrator.calls[0]["excluded_tools"] is None

    db.close()


def test_order_collection_delivery_question_keeps_collecting():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-delivery-1",
            "quero 2 x salada",
        ),
    )
    assert orchestrator.calls == []

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-delivery-2",
            "e sobre a entrega?",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "COLLECTING_ORDER"
    assert orchestrator.calls[0]["excluded_tools"] is not None

    db.close()


def test_order_collection_expired_state_returns_to_normal_olivia():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    # Inicia uma coleta normalmente, sem GPT.
    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-expired-1",
            "quero 2 x salada",
        ),
    )

    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    # Simula coleta abandonada ha mais de 2 horas.
    state.created_at = (
        datetime.now(timezone.utc) - timedelta(hours=3)
    )
    db.commit()

    # Nao deve continuar preso na coleta antiga.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-expired-2",
            "e uma batata",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1
    assert (
        orchestrator.calls[0]["customer_message"]
        == "e uma batata"
    )
    assert orchestrator.calls[0]["extra_instructions"] is None
    assert orchestrator.calls[0]["excluded_tools"] is None

    db.close()


def test_order_collection_menu_request_keeps_full_non_order_capability():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-menu-1",
            "quero 2 x salada",
        ),
    )
    assert orchestrator.calls == []

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-menu-2",
            "manda o cardápio",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1

    blocked = orchestrator.calls[0]["excluded_tools"]
    assert blocked == {
        "get_or_create_cart",
        "add_cart_item",
        "update_cart_item",
        "remove_cart_item",
        "checkout_cart",
    }
    assert "send_menu_pdf" not in blocked
    assert "request_human_help" not in blocked
    assert "report_order_issue" not in blocked

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "COLLECTING_ORDER"

    db.close()


def test_order_collection_payment_finish_triggers():
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    finish_messages = (
        "Pagamento no pix",
        "Vou pagar no pix",
        "PIX",
        "Chave pix",
        "Manda a chave pix",
        "Esperando a chave",
        "Pagamento no cartão",
        "Pagamento no crédito",
        "Pagamento no débito",
        "Pagamento em dinheiro",
        "Troco para 50",
    )

    for message in finish_messages:
        assert service._is_order_collection_finish_trigger(message)

    assert not service._is_order_collection_finish_trigger(
        "Aceita pix?"
    )
    assert not service._is_order_collection_finish_trigger(
        "Tem desconto no pix?"
    )


def test_release_to_olivia_resolves_active_human_tickets():
    from app.services.conversation import ConversationService

    db, store, _ = setup_db()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597000000000",
        status="HUMAN",
    )
    db.add(conversation)
    db.flush()

    ticket_open = HumanTicket(
        store_id=store.id,
        conversation_id=conversation.id,
        category="OTHER",
        priority="URGENT",
        status="OPEN",
        reason="Teste ticket aberto",
        customer_message="Preciso de ajuda",
    )

    ticket_progress = HumanTicket(
        store_id=store.id,
        conversation_id=conversation.id,
        category="OTHER",
        priority="URGENT",
        status="IN_PROGRESS",
        reason="Teste ticket em atendimento",
        customer_message="Continuo precisando de ajuda",
    )

    db.add_all([ticket_open, ticket_progress])
    db.commit()

    ConversationService().release_to_olivia(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente Teste",
    )

    db.refresh(conversation)
    db.refresh(ticket_open)
    db.refresh(ticket_progress)

    assert conversation.status == "OPEN"

    for ticket in (ticket_open, ticket_progress):
        assert ticket.status == "RESOLVED"
        assert ticket.assigned_to == "Atendente Teste"
        assert "olívia" in ticket.resolution.lower()

    event = db.scalar(
        select(AIEvent).where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "HUMAN_RELEASE",
        )
    )

    assert event is not None

    db.close()


def test_order_collection_prep_time_uses_store_rule_zero_gpt():
    from app.models.commercial import StoreCommercialRules

    db, store, _ = setup_db()

    rules = db.scalar(
        select(StoreCommercialRules).where(
            StoreCommercialRules.store_id == store.id,
        )
    )

    if rules is None:
        rules = StoreCommercialRules(
            store_id=store.id,
        )
        db.add(rules)

    rules.average_prep_minutes = 20
    db.commit()

    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    # As frases operacionais de tempo devem ser reconhecidas
    # sem transformar perguntas de produto em tempo de preparo.
    for phrase in (
        "vai demorar?",
        "quanto tempo demora?",
        "qual o tempo?",
        "quanto tempo para ficar pronto?",
        "demora muito?",
    ):
        assert (
            service._is_order_collection_wait_time_question(
                phrase
            )
            is True
        )

    assert (
        service._is_order_collection_wait_time_question(
            "tem coca 1 litro?"
        )
        is False
    )

    # Inicia a coleta: zero GPT.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-prep-time-1",
            "quero 2 x salada",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    # Pergunta sobre demora: continua zero GPT.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-prep-time-2",
            "vai demorar?",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id
                == conversation.id,
                Message.direction == "OUTBOUND",
            )
            .order_by(Message.created_at)
        )
    )

    assert messages

    prep_reply = messages[-1]

    assert "20 minutos" in prep_reply.content
    assert (
        prep_reply.metadata_json["type"]
        == "ORDER_COLLECTION_PREP_TIME"
    )
    assert (
        prep_reply.metadata_json["deterministic"]
        is True
    )
    assert (
        prep_reply.metadata_json["openai_used"]
        is False
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type
            == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert (
        state.payload_json["state"]
        == "COLLECTING_ORDER"
    )

    # Depois da pergunta, continua coletando item
    # deterministicamente.
    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.collect-prep-time-3",
            "e uma batata",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    db.close()


def test_closed_store_contact_is_zero_gpt():
    db, store, _ = setup_db()

    store.operation_mode = "HUMAN_ONLY"
    db.commit()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    service.commercial_status.current_shift_window = (
        lambda db, store_id: {
            "active": False,
            "reliable": True,
            "started_at": None,
            "ends_at": None,
            "local_time": datetime(
                2026,
                9,
                3,
                2,
                0,
                tzinfo=timezone(timedelta(hours=-4)),
            ),
        }
    )

    result = service.process_payload(
        db,
        inbound_payload("wamid.closed-1"),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    messages = list(
        db.scalars(select(Message).order_by(Message.created_at))
    )

    assert len(messages) == 2
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[1].sender_type == "OLIVIA"

    assert (
        messages[1].metadata_json["openai_used"]
        is False
    )
    assert (
        messages[1].metadata_json["type"]
        == "STORE_CLOSED_AUTO_REPLY"
    )


def test_closed_store_repeated_message_does_not_spam_or_use_gpt():
    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    service.commercial_status.current_shift_window = (
        lambda db, store_id: {
            "active": False,
            "reliable": True,
            "started_at": None,
            "ends_at": None,
            "local_time": datetime(
                2026,
                9,
                3,
                2,
                0,
                tzinfo=timezone(timedelta(hours=-4)),
            ),
        }
    )

    first = service.process_payload(
        db,
        inbound_payload("wamid.closed-repeat-1"),
    )
    second = service.process_payload(
        db,
        inbound_payload("wamid.closed-repeat-2"),
    )

    assert first.failed == 0
    assert second.failed == 0
    assert orchestrator.calls == []

    messages = list(db.scalars(select(Message)))

    inbound = [
        item
        for item in messages
        if item.direction == "INBOUND"
    ]
    automatic = [
        item
        for item in messages
        if (
            item.metadata_json or {}
        ).get("type") == "STORE_CLOSED_AUTO_REPLY"
    ]

    assert len(inbound) == 2
    assert len(automatic) == 1

    outbounds = list(
        db.scalars(select(OutboundChannelMessage))
    )
    assert len(outbounds) == 1

    db.close()


def test_previous_shift_active_order_does_not_block_olivia():
    db, store, _ = setup_db()

    sender = "5597999999999"

    customer = Customer(
        store_id=store.id,
        name="Cliente Turno Anterior",
        phone=sender,
        active=True,
    )
    db.add(customer)
    db.flush()

    now = datetime.now(timezone.utc)
    shift_start = now - timedelta(hours=2)

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=uuid4(),
        display_id="000991",
        status="DISPATCHED",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("23.00"),
        customer_name=customer.name,
        customer_phone=sender,
    )

    # Simula um pedido antigo, de turno anterior.
    order.created_at = shift_start - timedelta(days=1)

    db.add(order)
    db.commit()

    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    service.commercial_status.current_shift_window = (
        lambda db, store_id: {
            "active": True,
            "reliable": True,
            "started_at": shift_start,
            "ends_at": now + timedelta(hours=4),
            "local_time": now,
        }
    )

    payload = inbound_payload(
        message_id="wamid.previous-shift-order"
    )
    message = payload["entry"][0]["changes"][0][
        "value"
    ]["messages"][0]
    message["text"]["body"] = "Olá"

    result = service.process_payload(db, payload)

    assert result.processed == 1
    assert result.failed == 0
    assert len(orchestrator.calls) == 1

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
            Conversation.customer_id == customer.id,
        )
    )

    assert conversation is not None
    assert conversation.status == "OPEN"

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id
                == conversation.id
            )
        )
    )

    assert tickets == []

    db.close()


def test_current_shift_active_order_still_blocks_olivia():
    db, store, _ = setup_db()

    sender = "5597999999999"

    customer = Customer(
        store_id=store.id,
        name="Cliente Turno Atual",
        phone=sender,
        active=True,
    )
    db.add(customer)
    db.flush()

    now = datetime.now(timezone.utc)
    shift_start = now - timedelta(hours=2)

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=uuid4(),
        display_id="000992",
        status="DISPATCHED",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("23.00"),
        customer_name=customer.name,
        customer_phone=sender,
    )

    order.created_at = shift_start + timedelta(minutes=30)

    db.add(order)
    db.commit()

    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    service.commercial_status.current_shift_window = (
        lambda db, store_id: {
            "active": True,
            "reliable": True,
            "started_at": shift_start,
            "ends_at": now + timedelta(hours=4),
            "local_time": now,
        }
    )

    payload = inbound_payload(
        message_id="wamid.current-shift-order"
    )
    message = payload["entry"][0]["changes"][0][
        "value"
    ]["messages"][0]
    message["text"]["body"] = "Olá"

    result = service.process_payload(db, payload)

    assert result.processed == 1
    assert result.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
            Conversation.customer_id == customer.id,
        )
    )

    assert conversation is not None
    assert conversation.status == "WAITING_HUMAN"

    db.close()


def test_order_collection_natural_finish_and_negative_triggers():
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    finish_messages = (
        "Já pode",
        "Nada mais",
        "Já pode montar",
        "Pode montar",
        "Só isso",
        "Somente isso",
        "É só isso",
    )

    for message in finish_messages:
        assert service._is_order_collection_finish_trigger(message), message

    continue_messages = (
        "Ainda não",
        "Não pode montar ainda",
        "Não pode montar",
        "Não terminei",
        "Não finalizei",
    )

    for message in continue_messages:
        assert not service._is_order_collection_finish_trigger(message), message



# MENU OPTIONS ZERO GPT

def _add_synchronized_menu_pdf(db: Session, store: Store) -> None:
    version = CatalogVersion(
        store_id=store.id,
        version_code=f"TEST-{uuid4()}",
        provider="GENERIC",
        status="ACTIVE",
        active=True,
    )
    db.add(version)
    db.flush()

    db.add(
        StoreMenuDocument(
            store_id=store.id,
            catalog_version_id=version.id,
            original_name="cardapio-teste.pdf",
            content_type="application/pdf",
            public_token=uuid4().hex,
            content=b"%PDF-1.4\n% teste",
        )
    )
    db.commit()


def _last_olivia_outbound(db: Session):
    return db.scalar(
        select(Message)
        .where(
            Message.direction == "OUTBOUND",
            Message.sender_type == "OLIVIA",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )


def test_menu_without_pdf_falls_back_to_olivia():
    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.menu-no-pdf",
            "manda o cardápio",
        ),
    )

    assert result.failed == 0
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["customer_message"] == "manda o cardápio"

    db.close()


def test_generic_menu_with_online_url_still_uses_pdf_first(monkeypatch):
    from app.core.config import settings

    db, store, _ = setup_db()

    monkeypatch.setattr(
        settings,
        "public_base_url",
        "https://smartfoodia.test",
    )
    orchestrator = FakeOrchestrator()

    online_url = "https://menu.exemplo.com/loja"

    db.add(
        StoreCommercialRules(
            store_id=store.id,
            online_order_url=online_url,
        )
    )
    db.commit()

    _add_synchronized_menu_pdf(db, store)

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.menu-with-url",
            "manda o cardápio",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    reply = _last_olivia_outbound(db)

    assert reply is not None
    assert "PDF" in reply.content
    assert online_url not in reply.content
    assert "cardápio online" not in reply.content.lower()
    assert reply.metadata_json["deterministic"] is True
    assert reply.metadata_json["openai_used"] is False
    assert reply.metadata_json["type"] == "MENU_PDF_SENT"

    db.close()


def test_explicit_online_menu_without_url_never_invents_link():
    db, _, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.menu-online-no-url",
            "manda o link do cardápio",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    reply = _last_olivia_outbound(db)

    assert "não há cardápio online configurado" in reply.content.lower()
    assert "PDF" in reply.content
    assert "http://" not in reply.content
    assert "https://" not in reply.content

    db.close()


def test_explicit_online_menu_uses_exact_configured_url():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    online_url = "https://menu.exemplo.com/oficial"

    db.add(
        StoreCommercialRules(
            store_id=store.id,
            online_order_url=online_url,
        )
    )
    db.commit()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.menu-online-url",
            "cardápio online",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    reply = _last_olivia_outbound(db)

    assert online_url in reply.content
    assert reply.content.count(online_url) == 1

    db.close()


def test_explicit_pdf_menu_is_deterministic_without_gpt(monkeypatch):
    from app.core.config import settings

    db, store, _ = setup_db()

    monkeypatch.setattr(
        settings,
        "public_base_url",
        "https://smartfoodia.test",
    )

    _add_synchronized_menu_pdf(db, store)

    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.menu-pdf",
            "manda o cardápio em PDF",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    db.close()


def test_menu_request_classifier_prefers_pdf_for_broad_discovery():
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    assert service._menu_request_kind(
        "quais hambúrgueres vocês têm?"
    ) == "MENU"

    assert service._menu_request_kind(
        "manda o cardápio em PDF"
    ) == "PDF"

    assert service._menu_request_kind(
        "quero 2 x salada"
    ) is None



def test_upsell_prompt_avoids_automatic_browse_catalog():
    assert (
        "Não use browse_catalog apenas para preparar uma oferta "
        "de complemento ou upsell."
        in OLIVIA_INSTRUCTIONS
    )
    assert (
        "cadastro ou alteração de endereço"
        in OLIVIA_INSTRUCTIONS
    )
    assert (
        "Se o cliente pedir opções, nomes, categorias ou preços "
        "de forma ampla"
        in OLIVIA_INSTRUCTIONS
    )


def test_post_checkout_courtesy_classifier_is_strict():
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    courtesy_messages = (
        "Ok",
        "OK!",
        "Certo",
        "Tá bom",
        "Obrigado",
        "Obrigada",
        "Obrigadaa",
        "Obg",
        "Ok obg",
        "Valeu",
        "👍",
        "🙏",
    )

    for message in courtesy_messages:
        assert service._is_post_checkout_courtesy(message), message

    human_messages = (
        "ok mas veio errado",
        "obrigado quero cancelar",
        "tá bom, quanto demora?",
        "beleza cadê meu pedido",
        "ok troca o endereço",
        "valeu mas não chegou",
        "meu pedido",
        "quanto tempo para entrega?",
        "quero falar com atendente",
        "olá",
    )

    for message in human_messages:
        assert not service._is_post_checkout_courtesy(message), message


def test_active_order_post_checkout_courtesy_does_not_route_to_human():
    db, store, _ = setup_db()

    sender = "5597999999999"

    customer = Customer(
        store_id=store.id,
        name="Cliente Cortesia Pós Checkout",
        phone=sender,
        active=True,
    )
    db.add(customer)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=uuid4(),
        display_id="000993",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("30.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("33.00"),
        customer_name=customer.name,
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

    payload = inbound_payload(
        message_id="wamid.post-checkout-courtesy-1"
    )

    message = payload["entry"][0]["changes"][0][
        "value"
    ]["messages"][0]

    message["text"]["body"] = "Ok obg"

    result = service.process_payload(db, payload)

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
            Conversation.customer_id == customer.id,
        )
    )

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id == conversation.id,
            )
        )
    )

    inbound = db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.direction == "INBOUND",
            Message.sender_type == "CUSTOMER",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )

    assert result.processed == 1
    assert result.failed == 0

    assert orchestrator.calls == []

    assert conversation.status == "OPEN"
    assert tickets == []

    assert inbound is not None
    assert inbound.content == "Ok obg"
    assert inbound.metadata_json["type"] == "POST_CHECKOUT_COURTESY"
    assert inbound.metadata_json["deterministic"] is True
    assert inbound.metadata_json["openai_used"] is False

    # A cortesia não gera resposta automática.
    olivia_outbounds = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.direction == "OUTBOUND",
                Message.sender_type == "OLIVIA",
            )
        )
    )

    assert olivia_outbounds == []

    db.close()



def test_pix_needs_review_is_visible_in_central_and_opens_human_ticket(
    tmp_path,
):
    from app.services.conversation_media import ConversationMediaStorage

    db, store, account = setup_db()

    sender = "5597999999999"

    customer = Customer(
        store_id=store.id,
        name="Cliente PIX Revisao",
        phone=sender,
        active=True,
    )
    db.add(customer)
    db.flush()

    conversation = Conversation(
        store_id=store.id,
        customer_id=customer.id,
        channel="WHATSAPP",
        external_conversation_id=sender,
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    order = Order(
        store_id=store.id,
        customer_id=customer.id,
        cart_id=uuid4(),
        display_id="000991",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PREPAID",
        subtotal=Decimal("24.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("27.00"),
        customer_name=customer.name,
        customer_phone=sender,
    )
    db.add(order)
    db.flush()

    event = ChannelEvent(
        channel_account_id=account.id,
        provider="WHATSAPP_CLOUD",
        external_event_id="wamid.pix-needs-review-central",
        event_type="INBOUND_MESSAGE",
        payload_json={},
    )
    db.add(event)
    db.commit()

    service = PixReceiptService(
        conversation_media_storage=ConversationMediaStorage(
            root_path=tmp_path,
        ),
    )

    service._recent_pix_orders = (
        lambda *args, **kwargs: [order]
    )

    notify_calls = []

    def fake_notify_review(
        db_session,
        *,
        account,
        receipt,
    ):
        notify_calls.append(receipt.id)
        return 1

    service.review.notify_review = fake_notify_review

    def fake_validate(
        db_session,
        *,
        receipt,
    ):
        receipt.status = "NEEDS_REVIEW"
        receipt.validation_json = {
            **(receipt.validation_json or {}),
            "decision": "NEEDS_REVIEW",
            "reasons": [
                "RECEIVER_NOT_CONFIRMED",
            ],
        }
        db_session.commit()
        db_session.refresh(receipt)
        return receipt

    service.validator.process = fake_validate

    result = service.receive_whatsapp_media(
        db,
        account=account,
        event=event,
        conversation=conversation,
        sender=sender,
        message={
            "type": "image",
            "image": {
                "id": "media-pix-needs-review",
                "mime_type": "image/png",
            },
        },
        client=FakeClient(),
        allow_customer_reply=True,
    )

    assert result is not None
    assert result.status == "NEEDS_REVIEW"

    receipts = list(
        db.scalars(
            select(PaymentReceipt).where(
                PaymentReceipt.order_id == order.id
            )
        )
    )

    assert len(receipts) == 1
    assert receipts[0].status == "NEEDS_REVIEW"

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "INBOUND",
                Message.sender_type == "CUSTOMER",
            )
        )
    )

    assert len(messages) == 1

    message = messages[0]

    assert message.content == "[Comprovante PIX recebido]"
    assert message.content_type == "IMAGE"

    metadata = message.metadata_json

    assert metadata["payment_receipt_id"] == str(
        receipts[0].id
    )
    assert (
        metadata["payment_receipt_status"]
        == "NEEDS_REVIEW"
    )
    assert metadata["stored_media"] is True
    assert metadata["mime_type"] == "image/png"

    stored_path = (
        tmp_path
        / metadata["stored_media_path"]
    )

    assert stored_path.is_file()
    assert (
        stored_path.read_bytes()
        == b"imagem-teste-whatsapp"
    )

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.conversation_id
                == conversation.id
            )
        )
    )

    assert len(tickets) == 1
    assert tickets[0].status == "OPEN"
    assert tickets[0].priority == "URGENT"
    assert "PIX do pedido #000991" in tickets[0].reason

    db.refresh(conversation)

    assert conversation.status == "WAITING_HUMAN"

    assert notify_calls == [receipts[0].id]

    validation = receipts[0].validation_json or {}

    assert validation["staff_review_notified"] is True
    assert validation["staff_review_notified_count"] == 1

    customer_outbounds = list(
        db.scalars(
            select(OutboundChannelMessage).where(
                OutboundChannelMessage.recipient == sender
            )
        )
    )

    # Continua existindo apenas a resposta PIX original.
    # O handoff não envia uma segunda resposta automática.
    assert len(customer_outbounds) == 1
    assert "conferência" in customer_outbounds[0].content

    ai_events = list(
        db.scalars(
            select(AIEvent).where(
                AIEvent.conversation_id == conversation.id
            )
        )
    )

    assert any(
        event.event_type == "HUMAN_WAITING"
        for event in ai_events
    )

    assert not any(
        event.event_type == "AI_RESPONSE"
        for event in ai_events
    )

    db.close()


def test_mixed_checkout_generates_pix_code_only_for_pix_part():
    db, store, _ = setup_db()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597999999999",
        status="OPEN",
    )
    db.add(conversation)
    db.flush()

    db.add(
        StoreCommercialRules(
            store_id=store.id,
            accepts_pix=True,
            pix_key="pix@oldburguer87.com",
            pix_receiver_name="OLD BURGUER 87",
        )
    )

    db.add(
        AIEvent(
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
                        "display_id": "000990",
                        "payment_method": "MIXED",
                        "total": 65.00,
                        "payments": [
                            {
                                "method": "PIX",
                                "payment_type": "PREPAID",
                                "amount": 30.00,
                                "position": 1,
                            },
                            {
                                "method": "CASH",
                                "payment_type": "PENDING",
                                "amount": 35.00,
                                "position": 2,
                            },
                        ],
                    },
                },
            },
        )
    )
    db.commit()

    service = WhatsAppGatewayService()

    result = service._pix_after_recent_checkout(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        since=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    assert result is not None
    assert result["display_id"] == "000990"
    assert result["total"] == "30,00"

    # Tag EMV 54 = valor da cobrança PIX.
    assert "540530.00" in result["code"]
    assert "540565.00" not in result["code"]


def test_mixed_pix_checkout_enables_receipt_candidate():
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
        display_id="000991",
        status="READY_FOR_INTEGRATION",
        service_mode="TAKEOUT",
        payment_method="MIXED",
        payment_type="PENDING",
        subtotal=Decimal("65.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("65.00"),
        customer_name="Cliente Misto",
        customer_phone=sender,
    )
    db.add(order)
    db.flush()

    db.add_all([
        OrderPayment(
            order_id=order.id,
            method="PIX",
            payment_type="PREPAID",
            amount=Decimal("30.00"),
            position=1,
        ),
        OrderPayment(
            order_id=order.id,
            method="CASH",
            payment_type="PENDING",
            amount=Decimal("35.00"),
            position=2,
        ),
    ])

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="checkout_cart",
            success=True,
            payload_json={
                "result": {
                    "ok": True,
                    "data": {
                        "id": str(order.id),
                        "display_id": order.display_id,
                        "payment_method": "MIXED",
                        "total": 65.00,
                        "payments": [
                            {"method": "PIX", "amount": 30.00},
                            {"method": "CASH", "amount": 35.00},
                        ],
                    },
                },
            },
        )
    )

    db.commit()

    candidates = PixReceiptService()._recent_pix_orders(
        db,
        store_id=store.id,
        customer_phone=sender,
        conversation_id=conversation.id,
    )

    assert len(candidates) == 1
    assert candidates[0].id == order.id
    assert candidates[0].payment_method == "MIXED"


def test_order_collection_real_world_finish_phrases_from_order_000080():
    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    messages = (
        "Somente",
        "Sim.pode",
        "Simm pode",
        "Pode montarrrrr",
        "Manda o pix",
        "Mamda o pix",
        "Confirmado por favor quero pagar e monta logo",
    )

    for message in messages:
        assert service._is_order_collection_finish_trigger(message), message


def test_order_collection_order_000080_somente_releases_to_olivia():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.loop-80-1",
            "Quero um XBurguer",
        ),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.loop-80-2",
            "Entregar Rua 03 numero 40",
        ),
    )

    assert orchestrator.calls == []

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.loop-80-3",
            "Somente",
        ),
    )

    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["customer_message"] == "Somente"

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "NORMAL"
    assert state.payload_json["reason"] == "customer_ready_to_mount"

    db.close()


def test_order_collection_ack_loop_fuse_prevents_third_ack():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    for message_id, body in (
        ("wamid.fuse-1", "Quero um XBurguer"),
        ("wamid.fuse-2", "Rua 03 numero 40"),
        ("wamid.fuse-3", "Casa branca de canto"),
        ("wamid.fuse-4", "Conjunto Naide Lins"),
    ):
        service.process_payload(
            db,
            _order_collection_payload(message_id, body),
        )

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    acknowledgements = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.sender_type == "OLIVIA",
            )
        )
    )

    ack_count = sum(
        1
        for message in acknowledgements
        if (message.metadata_json or {}).get("type")
        == "ORDER_COLLECTION_ITEM_ACK"
    )

    assert ack_count == 2
    assert len(orchestrator.calls) == 1

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "NORMAL"
    assert state.payload_json["reason"] == "order_collection_ack_loop_fuse"

    db.close()


def test_human_takeover_resets_order_collection_state():
    from app.services.conversation import ConversationService

    db, store, _ = setup_db()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: FakeOrchestrator(),
        client_factory=lambda: FakeClient(),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.takeover-reset-1",
            "Quero um XBurguer",
        ),
    )

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    ConversationService().take_over(
        db,
        conversation_id=conversation.id,
        assigned_to="Atendente Teste",
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "NORMAL"
    assert state.payload_json["reason"] == "human_takeover"

    db.close()


def test_receipt_question_is_answered_deterministically_and_registered():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()
    client = FakeClient()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: client,
    )

    result = service.process_payload(
        db,
        _order_collection_payload(
            "wamid.receipt-paloma-1",
            "Adicionalmente, vcs emitem nota fiscal ou recibo?",
        ),
    )

    assert result.failed == 0
    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    event = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_RECEIPT_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert event is not None
    assert event.payload_json["requested"] is True

    reply = db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.direction == "OUTBOUND",
            Message.sender_type == "OLIVIA",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )

    assert "emitimos recibo" in reply.content.lower()
    assert "emitimos nota fiscal" not in reply.content.lower()

    db.close()


def test_receipt_request_during_collection_does_not_trigger_item_ack():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.receipt-collect-1",
            "Quero um XBurguer",
        ),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.receipt-collect-2",
            "Tras um recibo por favor",
        ),
    )

    assert orchestrator.calls == []

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "COLLECTING_ORDER"

    receipt = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_RECEIPT_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert receipt.payload_json["requested"] is True

    db.close()


def test_order_collection_frustration_releases_to_olivia_without_another_ack():
    db, store, _ = setup_db()
    orchestrator = FakeOrchestrator()

    service = WhatsAppGatewayService(
        orchestrator_factory=lambda: orchestrator,
        client_factory=lambda: FakeClient(),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.frustration-1",
            "Quero um XBurguer",
        ),
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.frustration-2",
            "Rua Teste 123",
        ),
    )

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.store_id == store.id,
        )
    )

    before = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.direction == "OUTBOUND",
                Message.sender_type == "OLIVIA",
            )
        )
    )

    ack_before = sum(
        1
        for message in before
        if (message.metadata_json or {}).get("type")
        == "ORDER_COLLECTION_ITEM_ACK"
    )

    service.process_payload(
        db,
        _order_collection_payload(
            "wamid.frustration-3",
            "Ja fizeram essa pergunta umas cinco vezes",
        ),
    )

    after = list(
        db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.direction == "OUTBOUND",
                Message.sender_type == "OLIVIA",
            )
        )
    )

    ack_after = sum(
        1
        for message in after
        if (message.metadata_json or {}).get("type")
        == "ORDER_COLLECTION_ITEM_ACK"
    )

    assert ack_after == ack_before
    assert len(orchestrator.calls) == 1

    state = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.conversation_id == conversation.id,
            AIEvent.event_type == "ORDER_COLLECTION_STATE",
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    assert state.payload_json["state"] == "NORMAL"
    assert (
        state.payload_json["reason"]
        == "customer_frustrated_release_to_olivia"
    )

    db.close()
