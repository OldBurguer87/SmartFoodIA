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
from app.services.human_relay import HumanRelayService
from app.services.pix_receipt import PixReceiptService


class WhatsAppWebhookError(ValueError):
    pass


def normalize_whatsapp_recipient(value: str) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())

    if (
        digits.startswith("55")
        and len(digits) == 12
        and digits[4] in "6789"
    ):
        return f"{digits[:4]}9{digits[4:]}"

    return digits


def sanitize_whatsapp_text(value: str) -> str:
    """Keep Olivia's WhatsApp replies plain and readable.

    The prompt asks for plain text, but this defensive layer removes common
    Markdown artifacts if a model response still contains them.
    """
    text = str(value).replace("`", "").replace("*", "")
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            prefix_len = len(line) - len(stripped)
            stripped = stripped.lstrip("#").lstrip()
            line = (" " * prefix_len) + stripped
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


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
        self.human_relay = HumanRelayService()
        self.pix_receipts = PixReceiptService()

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
                    event_id = (
                        f"status:{status.get('id')}:"
                        f"{status.get('status')}"
                    )

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

                    event.status = "RECEIVED"
                    event.next_attempt_at = None
                    db.commit()

                    if not self.process_inline:
                        processed += 1
                        continue

                    try:
                        self.process_event(
                            db,
                            account,
                            event,
                        )
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

                        WhatsAppQueueProcessor(
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

    def process_event(
        self,
        db: Session,
        account: ChannelAccount,
        event: ChannelEvent,
    ) -> None:
        if event.event_type == "MESSAGE_STATUS":
            self._process_message_status(
                db,
                account,
                event,
                event.payload_json,
            )
            return

        if event.event_type != "INBOUND_MESSAGE":
            event.status = "IGNORED"
            return

        self._process_message(
            db,
            account,
            event,
            event.payload_json,
        )

    def _process_message_status(
        self,
        db: Session,
        account: ChannelAccount,
        event: ChannelEvent,
        status: dict[str, Any],
    ) -> None:
        external_message_id = str(
            status.get("id") or ""
        ).strip()

        if not external_message_id:
            raise WhatsAppWebhookError(
                "MESSAGE_STATUS sem ID da mensagem."
            )

        outbound = (
            self.repository
            .get_outbound_by_external_message_id(
                db,
                provider=account.provider,
                external_message_id=external_message_id,
            )
        )

        if outbound is None:
            event.status = "IGNORED"
            event.error_message = (
                "Mensagem de saída não localizada para "
                f"external_message_id={external_message_id}"
            )
            return

        meta_status = str(
            status.get("status") or ""
        ).strip().lower()

        status_map = {
            "sent": "SENT_TO_META",
            "delivered": "DELIVERED",
            "read": "READ",
            "failed": "FAILED",
        }

        target_status = status_map.get(meta_status)

        if target_status is None:
            event.status = "IGNORED"
            event.error_message = (
                f"Status WhatsApp não tratado: {meta_status!r}"
            )
            return

        # Evita regressão caso webhooks cheguem fora de ordem.
        progress = {
            "SENT": 1,          # legado
            "SENT_TO_META": 1,
            "DELIVERED": 2,
            "READ": 3,
        }

        if target_status == "FAILED":
            outbound.status = "FAILED"

            errors = status.get("errors") or []
            messages: list[str] = []

            for error in errors[:3]:
                if not isinstance(error, dict):
                    continue

                code = error.get("code")
                title = (
                    error.get("title")
                    or error.get("message")
                    or "WhatsApp error"
                )

                error_data = error.get("error_data") or {}
                details = (
                    error_data.get("details")
                    if isinstance(error_data, dict)
                    else None
                )

                part = (
                    f"{code}: {title}"
                    if code is not None
                    else str(title)
                )

                if details:
                    part += f" | {details}"

                messages.append(part)

            outbound.error_message = (
                " | ".join(messages)
                or "WhatsApp informou falha na entrega."
            )

        else:
            current_rank = progress.get(
                outbound.status,
                0,
            )
            target_rank = progress[target_status]

            if target_rank >= current_rank:
                outbound.status = target_status

            outbound.error_message = None

    def _process_message(
        self,
        db: Session,
        account: ChannelAccount,
        event: ChannelEvent,
        message: dict[str, Any],
    ) -> None:
        raw_sender = str(message.get("from") or "")
        sender = normalize_whatsapp_recipient(raw_sender)
        message_type = str(message.get("type") or "").lower()

        if not sender:
            raise WhatsAppWebhookError("Mensagem sem remetente.")

        staff = self.human_relay.get_staff_sender(
            db,
            store_id=account.store_id,
            phone=sender,
        )

        if message_type in {"image", "document"}:
            if staff is not None:
                event.status = "IGNORED"
                event.error_message = (
                    "Mídia enviada por membro da equipe ainda não "
                    "é tratada como comando."
                )
                return

            conversation = self.conversations.get_or_create(
                db,
                ConversationCreate(
                    store_id=account.store_id,
                    channel="WHATSAPP",
                    external_conversation_id=sender,
                ),
            )

            # Em atendimento humano, imagem/documento pertence à
            # conversa com o atendente e nunca deve ser analisado como PIX.
            if conversation.status == "HUMAN":
                media_payload = message.get(message_type) or {}
                media_id = str(
                    media_payload.get("id") or ""
                ).strip()

                if not media_id:
                    raise WhatsAppWebhookError(
                        "Mensagem de mídia sem media_id."
                    )

                filename = (
                    str(media_payload.get("filename") or "").strip()
                    if message_type == "document"
                    else None
                )

                caption = str(
                    media_payload.get("caption") or ""
                ).strip() or None

                history_content = (
                    "[Imagem recebida]"
                    if message_type == "image"
                    else (
                        f"[Documento recebido: {filename}]"
                        if filename
                        else "[Documento recebido]"
                    )
                )

                if caption:
                    history_content += f" {caption}"

                forwarded = (
                    self.human_relay.forward_customer_media_to_staff(
                        db,
                        account=account,
                        conversation=conversation,
                        media_id=media_id,
                        media_type=message_type,
                        filename=filename,
                        caption=caption,
                    )
                )

                if not forwarded:
                    raise WhatsAppWebhookError(
                        "Conversa HUMAN sem atendente vinculado "
                        "para receber a mídia."
                    )

                self.conversations.add_message(
                    db,
                    conversation_id=conversation.id,
                    payload=MessageCreate(
                        direction="INBOUND",
                        sender_type="CUSTOMER",
                        content_type=message_type.upper(),
                        content=history_content,
                        external_message_id=event.external_event_id,
                        metadata_json={
                            "media_id": media_id,
                            "media_type": message_type,
                            "filename": filename,
                            "caption": caption,
                        },
                    ),
                )
                return

            if self.client_factory is None:
                raise WhatsAppWebhookError(
                    "Cliente WhatsApp não disponível para baixar mídia."
                )

            self.pix_receipts.receive_whatsapp_media(
                db,
                account=account,
                event=event,
                conversation=conversation,
                sender=sender,
                message=message,
                client=self.client_factory(),
                allow_customer_reply=(
                    conversation.status == "OPEN"
                ),
            )
            return

        if message_type == "button":
            button = message.get("button") or {}

            button_payload = str(
                button.get("payload") or ""
            ).strip()

            button_text = str(
                button.get("text") or ""
            ).strip()

            # Para membros da equipe usamos o payload interno,
            # que é estável mesmo se o texto visível do botão mudar.
            if staff is not None and button_payload:
                body = button_payload
            else:
                body = button_text or button_payload

        elif message_type == "text":
            body = str(
                (message.get("text") or {}).get("body") or ""
            ).strip()

        elif message_type == "location":
            location = message.get("location") or {}

            latitude = location.get("latitude")
            longitude = location.get("longitude")
            name = str(location.get("name") or "").strip()
            address = str(location.get("address") or "").strip()

            if latitude is None or longitude is None:
                raise WhatsAppWebhookError(
                    "Localização recebida sem latitude/longitude."
                )

            parts = [
                "📍 Localização compartilhada pelo cliente",
            ]

            if name:
                parts.append(f"Local: {name}")

            if address:
                parts.append(f"Endereço: {address}")

            parts.extend(
                [
                    f"Latitude: {latitude}",
                    f"Longitude: {longitude}",
                    (
                        "Mapa: https://www.google.com/maps/search/"
                        f"?api=1&query={latitude},{longitude}"
                    ),
                ]
            )

            body = "\n".join(parts)

        else:
            event.status = "IGNORED"
            event.error_message = (
                f"Tipo ainda não suportado: "
                f"{message_type or 'desconhecido'}"
            )
            return

        if not body:
            raise WhatsAppWebhookError(
                "Mensagem recebida sem conteúdo utilizável."
            )

        if staff is not None:
            self.human_relay.handle_staff_message(
                db,
                account=account,
                staff=staff,
                body=body,
            )
            return

        conversation = self.conversations.get_or_create(
            db,
            ConversationCreate(
                store_id=account.store_id,
                channel="WHATSAPP",
                external_conversation_id=sender,
            ),
        )
        if conversation.status in {
            "WAITING_HUMAN",
            "RESUMING_OLIVIA",
            "HUMAN",
        }:
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

            if conversation.status == "HUMAN":
                self.human_relay.forward_customer_message_to_staff(
                    db,
                    account=account,
                    conversation=conversation,
                    body=body,
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
            content=sanitize_whatsapp_text(reply),
        )
