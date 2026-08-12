from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.openai_provider import OpenAIResponsesProvider
from app.channels.whatsapp.client import WhatsAppCloudClient
from app.models.channel import ChannelAccount, ChannelEvent
from app.repositories.channel import ChannelRepository
from app.schemas.conversation import ConversationCreate, MessageCreate
from app.services.conversation import ConversationService


class WhatsAppWebhookError(ValueError):
    pass


def normalize_whatsapp_recipient(value: str) -> str:
    """Normalize a WhatsApp recipient without changing valid international numbers.

    Meta may deliver some Brazilian mobile senders in the legacy 8-digit local
    format. For Brazil (+55), a 12-digit E.164-like value means 55 + DDD +
    8-digit local number. When that local number begins with 6-9 (mobile
    range), insert the Brazilian ninth digit after the DDD.

    Landlines (local number beginning with 2-5) and non-Brazilian numbers are
    left unchanged.
    """
    digits = "".join(character for character in str(value) if character.isdigit())

    if (
        digits.startswith("55")
        and len(digits) == 12
        and digits[4] in "6789"
    ):
        return f"{digits[:4]}9{digits[4:]}"

    return digits


@dataclass(frozen=True)
class WebhookProcessingResult:
    received: int = 0
    processed: int = 0
    duplicated: int = 0
    ignored: int = 0
    failed: int = 0


class WhatsAppGatewayService:
    def __init__(
        self,
        *,
        repository: ChannelRepository | None = None,
        conversation_service: ConversationService | None = None,
        orchestrator_factory: Callable[[], OliviaOrchestrator] | None = None,
        client_factory: Callable[[], WhatsAppCloudClient] | None = None,
        process_inline: bool = True,
    ) -> None:
        self.repository = repository or ChannelRepository()
        self.conversations = conversation_service or ConversationService()
        self.orchestrator_factory = orchestrator_factory or (
            lambda: OliviaOrchestrator(OpenAIResponsesProvider())
        )
        self.client_factory = client_factory
        self.process_inline = process_inline

    def process_payload(self, db: Session, payload: dict[str, Any]) -> WebhookProcessingResult:
        received = processed = duplicated = ignored = failed = 0

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value") or {}
                phone_number_id = str(
                    (value.get("metadata") or {}).get("phone_number_id") or ""
                )
                if not phone_number_id:
                    ignored += 1
                    continue
                account = self.repository.get_account_by_external_id(
                    db,
                    provider="WHATSAPP_CLOUD",
                    external_account_id=phone_number_id,
                )
                if account is None:
                    ignored += 1
                    continue

                for status in value.get("statuses", []) or []:
                    received += 1
                    event_id = f"status:{status.get('id')}:{status.get('status')}"
                    if self.repository.get_event(
                        db,
                        provider=account.provider,
                        external_event_id=event_id,
                    ):
                        duplicated += 1
                        continue
                    event = self.repository.create_event(
                        db,
                        account=account,
                        external_event_id=event_id,
                        event_type="MESSAGE_STATUS",
                        payload=status,
                    )
                    event.status = "PROCESSED"
                    db.commit()
                    processed += 1

                for message in value.get("messages", []) or []:
                    received += 1
                    external_message_id = str(message.get("id") or "")
                    if not external_message_id:
                        ignored += 1
                        continue
                    existing = self.repository.get_event(
                        db,
                        provider=account.provider,
                        external_event_id=external_message_id,
                    )
                    if existing is not None:
                        duplicated += 1
                        continue
                    event = self.repository.create_event(
                        db,
                        account=account,
                        external_event_id=external_message_id,
                        event_type="INBOUND_MESSAGE",
                        payload=message,
                    )
                    event.status = "RECEIVED"
                    event.next_attempt_at = None
                    db.commit()
                    if not self.process_inline:
                        processed += 1
                        continue
                    try:
                        self.process_event(db, account, event)
                        event.attempts += 1
                        if event.status == "IGNORED":
                            ignored += 1
                        else:
                            event.status = "PROCESSED"
                            processed += 1
                    except Exception as error:
                        event.status = "FAILED"
                        event.attempts += 1
                        event.error_message = str(error)
                        failed += 1
                    db.commit()
                    if event.status == "PROCESSED" and self.client_factory is not None:
                        from app.channels.whatsapp.queue import WhatsAppQueueProcessor

                        queue_result = WhatsAppQueueProcessor(
                            repository=self.repository,
                            client_factory=self.client_factory,
                        ).run_once(db)

        return WebhookProcessingResult(
            received=received,
            processed=processed,
            duplicated=duplicated,
            ignored=ignored,
            failed=failed,
        )

    def process_event(self, db: Session, account: ChannelAccount, event: ChannelEvent) -> None:
        if event.event_type != "INBOUND_MESSAGE":
            event.status = "IGNORED"
            return
        self._process_message(db, account, event, event.payload_json)

    def _process_message(
        self,
        db: Session,
        account: ChannelAccount,
        event: ChannelEvent,
        message: dict[str, Any],
    ) -> None:
        raw_sender = str(message.get("from") or "")
        sender = normalize_whatsapp_recipient(raw_sender)
        message_type = str(message.get("type") or "")
        if not sender:
            raise WhatsAppWebhookError("Mensagem sem remetente.")
        if message_type != "text":
            event.status = "IGNORED"
            event.error_message = f"Tipo ainda não suportado: {message_type or 'desconhecido'}"
            return
        body = str((message.get("text") or {}).get("body") or "").strip()
        if not body:
            raise WhatsAppWebhookError("Mensagem de texto vazia.")
        conversation = self.conversations.get_or_create(
            db,
            ConversationCreate(
                store_id=account.store_id,
                channel="WHATSAPP",
                external_conversation_id=sender,
            ),
        )
        if conversation.status == "HUMAN":
            self.conversations.add_message(
                db,
                conversation_id=conversation.id,
                payload=MessageCreate(
                    direction="INBOUND",
                    sender_type="CUSTOMER",
                    content=body,
                    external_message_id=event.external_event_id,
                ),
            )
            return
        reply = self.orchestrator_factory().reply(
            db,
            store_id=account.store_id,
            conversation_id=conversation.id,
            customer_message=body,
            customer_phone=sender,
        )
        self.repository.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=sender,
            content=reply,
        )
