from uuid import uuid4

import hashlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.channels.whatsapp.client import DownloadedMedia
from app.channels.whatsapp.security import hash_verify_token, verify_meta_signature
from app.channels.whatsapp.service import WhatsAppGatewayService
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage
from app.models.conversation import Conversation, Message
from app.models.payment import PaymentReceipt
from app.services.pix_receipt import PixReceiptService


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

    def send_text(self, **kwargs):
        self.sent.append(kwargs)
        return "wamid.outbound-1"

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
    assert "pedido PIX recente" in outbound.content
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
