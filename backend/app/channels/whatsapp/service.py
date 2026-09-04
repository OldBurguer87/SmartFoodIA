from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import unicodedata
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.openai_provider import (
    OpenAIProviderRequestError,
    OpenAIResponsesProvider,
)
from app.channels.whatsapp.client import WhatsAppCloudClient
from app.core.config import settings
from app.models.channel import ChannelAccount, ChannelEvent
from app.models.customer import Customer
from app.models.conversation import AIEvent
from app.models.commercial import StoreCommercialRules
from app.repositories.channel import ChannelRepository
from app.repositories.order import OrderRepository
from app.schemas.conversation import (
    AIEventCreate,
    ConversationCreate,
    HumanTicketCreate,
    MessageCreate,
)
from app.services.conversation import ConversationService
from app.services.conversation_media import ConversationMediaStorage
from app.services.commercial_status import CommercialStatusService
from app.services.human_relay import HumanRelayService
from app.services.operation_mode import is_store_human_only
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
    text = (
        str(value)
        .replace("`", "")
        .replace("*", "")
        .replace("\ufffd", "")
    )
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
        conversation_media_storage: ConversationMediaStorage | None = None,
        process_inline: bool = True,
    ) -> None:
        self.repository = repository or ChannelRepository()
        self.orders = OrderRepository()
        self.conversations = conversation_service or ConversationService()
        self.orchestrator_factory = orchestrator_factory or (
            lambda: OliviaOrchestrator(OpenAIResponsesProvider())
        )
        self.client_factory = client_factory
        self.process_inline = process_inline
        self.human_relay = HumanRelayService()
        self.pix_receipts = PixReceiptService()
        self.commercial_status = CommercialStatusService()
        self.conversation_media = (
            conversation_media_storage
            or ConversationMediaStorage()
        )

    @staticmethod
    def _normalize_order_collection_text(value: str) -> str:
        normalized = unicodedata.normalize(
            "NFKD",
            str(value or "").lower(),
        )
        return "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        ).strip()

    def _order_collection_state(
        self,
        db: Session,
        *,
        conversation_id: Any,
    ) -> str:
        event = db.scalar(
            select(AIEvent)
            .where(
                AIEvent.conversation_id == conversation_id,
                AIEvent.event_type == "ORDER_COLLECTION_STATE",
            )
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        if event is None:
            return "NORMAL"

        created_at = event.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(
                tzinfo=timezone.utc,
            )

        if (
            datetime.now(timezone.utc) - created_at
            > timedelta(hours=2)
        ):
            return "NORMAL"

        payload = event.payload_json or {}
        state = str(payload.get("state") or "NORMAL").upper()

        if state not in {
            "NORMAL",
            "COLLECTING_ORDER",
            "AWAITING_EXTRA",
        }:
            return "NORMAL"

        return state

    def _set_order_collection_state(
        self,
        db: Session,
        *,
        store_id: Any,
        conversation_id: Any,
        state: str,
        reason: str,
    ) -> None:
        self.conversations.record_event(
            db,
            store_id=store_id,
            payload=AIEventCreate(
                conversation_id=conversation_id,
                event_type="ORDER_COLLECTION_STATE",
                success=True,
                payload_json={
                    "state": state,
                    "reason": reason,
                },
            ),
        )

    def _send_order_collection_message(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        conversation: Any,
        recipient: str,
        content: str,
        prompt_type: str,
    ) -> None:
        self.conversations.add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction="OUTBOUND",
                sender_type="OLIVIA",
                content=content,
                metadata_json={
                    "type": prompt_type,
                    "deterministic": True,
                    "openai_used": False,
                },
            ),
        )

        self.repository.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=recipient,
            content=content,
        )

    def _active_order_blocks_olivia(
        self,
        db: Session,
        *,
        store_id,
        order,
    ) -> bool:
        shift = self.commercial_status.current_shift_window(
            db,
            store_id,
        )

        # Sem horário confiável ou fora de um turno ativo,
        # preserva a proteção anterior.
        if (
            not shift.get("reliable")
            or not shift.get("active")
            or shift.get("started_at") is None
        ):
            return True

        reference_at = (
            order.scheduled_for
            or order.created_at
        )

        if reference_at.tzinfo is None:
            reference_at = reference_at.replace(
                tzinfo=timezone.utc,
            )

        shift_start = shift["started_at"]

        if shift_start.tzinfo is None:
            shift_start = shift_start.replace(
                tzinfo=timezone.utc,
            )

        return (
            reference_at.astimezone(timezone.utc)
            >= shift_start.astimezone(timezone.utc)
        )

    def _handle_closed_store_contact(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        conversation: Any,
        event: ChannelEvent,
        recipient: str,
        content: str,
    ) -> bool:
        shift = self.commercial_status.current_shift_window(
            db,
            account.store_id,
        )

        if not shift["reliable"] or shift["active"]:
            return False

        self.conversations.add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content=content,
                external_message_id=event.external_event_id,
                metadata_json={
                    "type": "STORE_CLOSED_CONTACT",
                    "deterministic": True,
                    "openai_used": False,
                },
            ),
        )

        local_date = shift["local_time"].date().isoformat()

        previous = db.scalar(
            select(AIEvent)
            .where(
                AIEvent.conversation_id == conversation.id,
                AIEvent.event_type == "STORE_CLOSED_AUTO_REPLY",
            )
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        if (
            previous is not None
            and str(
                (previous.payload_json or {}).get("local_date")
                or ""
            )
            == local_date
        ):
            return True

        reply = (
            "Olá! No momento estamos fora do nosso horário "
            "de funcionamento. Quando estivermos abertos "
            "novamente, mande uma nova mensagem por aqui e "
            "continuamos seu atendimento. 😊"
        )

        self.conversations.add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction="OUTBOUND",
                sender_type="OLIVIA",
                content=reply,
                metadata_json={
                    "type": "STORE_CLOSED_AUTO_REPLY",
                    "deterministic": True,
                    "openai_used": False,
                },
            ),
        )

        self.repository.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=recipient,
            content=reply,
        )

        self.conversations.record_event(
            db,
            store_id=account.store_id,
            payload=AIEventCreate(
                conversation_id=conversation.id,
                event_type="STORE_CLOSED_AUTO_REPLY",
                success=True,
                payload_json={
                    "local_date": local_date,
                    "openai_used": False,
                },
            ),
        )

        return True

    def _save_order_collection_customer_message(
        self,
        db: Session,
        *,
        conversation_id: Any,
        event: ChannelEvent,
        content: str,
    ) -> None:
        self.conversations.add_message(
            db,
            conversation_id=conversation_id,
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content=content,
                external_message_id=event.external_event_id,
                metadata_json={
                    "type": "ORDER_COLLECTION_MESSAGE",
                },
            ),
        )

    def _is_explicit_new_order_request(
        self,
        value: str,
    ) -> bool:
        text = self._normalize_order_collection_text(value)

        if not text:
            return False

        if (
            self._is_order_collection_human_request(text)
            or self._is_order_collection_cancel(text)
        ):
            return False

        phrases = (
            "quero fazer outro pedido",
            "quero fazer um novo pedido",
            "quero outro pedido",
            "quero um novo pedido",
            "vou fazer outro pedido",
            "vou fazer um novo pedido",
            "fazer outro pedido",
            "fazer um novo pedido",
            "adicionar outro pedido",
            "abrir outro pedido",
            "iniciar outro pedido",
            "comecar outro pedido",
            "mais um pedido",
        )

        return any(phrase in text for phrase in phrases)

    def _is_order_collection_start(self, value: str) -> bool:
        text = self._normalize_order_collection_text(value)

        if not text:
            return False

        if (
            self._is_order_collection_human_request(text)
            or self._is_order_collection_cancel(text)
        ):
            return False

        if self._is_explicit_new_order_request(text):
            return True

        # Intencoes claramente informativas/operacionais devem continuar
        # sendo respondidas pela Olivia, e nunca iniciar coleta silenciosa.
        informational = (
            "quero saber",
            "queria saber",
            "gostaria de saber",
            "pode me dizer",
            "me diz",
            "me fala",
            "me informa",
            "cardapio",
            "disponivel",
            "reclama",
            "problema",
            "ajuda",
            "suporte",
            "alterar meu endereco",
            "mudar meu endereco",
            "trocar meu endereco",
        )

        if any(term in text for term in informational):
            return False

        explicit_order = (
            "quero fazer um pedido",
            "quero pedir",
            "vou fazer um pedido",
            "vou pedir",
        )

        if any(term in text for term in explicit_order):
            return True

        # Perguntas comuns continuam com Olivia imediatamente.
        # Excecao: uma mensagem que ja contem um pedido direto e tambem
        # um gatilho de encerramento/valor pode entrar na coleta.
        if "?" in text and not self._is_order_collection_finish_trigger(text):
            return False

        blocked = (
            "cardapio",
            "disponivel",
            "atendente",
            "humano",
            "gerente",
            "responsavel",
            "cancel",
            "nao quero",
        )

        if any(term in text for term in blocked):
            return False

        direct_order = (
            "vou querer ",
            "eu quero ",
            "quero ",
            "me ve ",
            "manda ",
        )

        return text.startswith(direct_order)

    def _is_order_collection_finish_trigger(
        self,
        value: str,
    ) -> bool:
        text = self._normalize_order_collection_text(value)
        compact = re.sub(r"\s+", " ", text).strip(" .,!?:;")

        # Gatilhos curtos precisam ser exatos para evitar falsos positivos
        # como "e sobre a entrega".
        exact = {
            "so isso",
            "e so isso",
            "e so",
            "pode fechar",
            "pode finalizar",
            "finaliza",
            "finalizar",
            "fechar pedido",
            "nao",
            "nao obrigado",
            "nao obrigada",
            "nao so isso",
            "ja pode montar",
            "pode montar",
            "pode montar o pedido",
            "pode montar meu pedido",
            "monta o pedido",
            "monta meu pedido",
        }

        if (
            compact in exact
            or any(
                compact.endswith(f" {trigger}")
                for trigger in exact
            )
        ):
            return True

        value_triggers = (
            "quanto ficou",
            "quanto deu",
            "qual o valor",
            "valor final",
            "valor do pedido",
            "total do pedido",
            "quanto custa",
            "valor do item",
            "preco do item",
        )

        if any(term in compact for term in value_triggers):
            return True

        payment_exact = {
            "pix",
            "no pix",
            "pelo pix",
            "cartao",
            "credito",
            "debito",
            "dinheiro",
        }

        if compact in payment_exact:
            return True

        payment_triggers = (
            "pagamento no pix",
            "pagamento pix",
            "pagar no pix",
            "vou pagar no pix",
            "pago no pix",
            "pode ser pix",
            "vai ser pix",
            "via pix",
            "pagamento via pix",
            "pagar via pix",
            "chave pix",
            "manda a chave pix",
            "manda a chave",
            "manda o pix",
            "me passa a chave pix",
            "me passa a chave",
            "qual a chave pix",
            "qual e a chave pix",
            "esperando a chave",
            "aguardando a chave",
            "pagamento no cartao",
            "pagamento em cartao",
            "vou pagar no cartao",
            "pode ser cartao",
            "pagar no credito",
            "pagamento no credito",
            "pagar no debito",
            "pagamento no debito",
            "pagamento em dinheiro",
            "vou pagar em dinheiro",
            "pagar em dinheiro",
            "troco para",
        )

        return any(
            term in compact
            for term in payment_triggers
        )

    def _is_order_collection_wait_time_question(
        self,
        value: str,
    ) -> bool:
        text = self._normalize_order_collection_text(value)

        if not text:
            return False

        triggers = (
            "vai demorar",
            "vai demora",
            "demora muito",
            "quanto demora",
            "quanto vai demorar",
            "quanto tempo",
            "qual o tempo",
            "tempo de preparo",
            "tempo para ficar pronto",
            "tempo pra ficar pronto",
            "quando fica pronto",
            "quando vai ficar pronto",
        )

        return any(
            trigger in text
            for trigger in triggers
        )

    def _order_collection_average_prep_minutes(
        self,
        db: Session,
        *,
        store_id: Any,
    ) -> int | None:
        value = db.scalar(
            select(
                StoreCommercialRules.average_prep_minutes
            ).where(
                StoreCommercialRules.store_id == store_id,
            )
        )

        if value is None:
            return None

        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return None

        return minutes if minutes > 0 else None

    def _is_order_collection_general_question(
        self,
        value: str,
    ) -> bool:
        text = self._normalize_order_collection_text(value)

        # Valor final/de item e encerramento seguem a regra aprovada:
        # primeiro pergunta se deseja acrescentar algo; GPT entra depois.
        if self._is_order_collection_finish_trigger(text):
            return False

        immediate_terms = (
            "cardapio",
            "menu",
            "reclama",
            "problema",
            "ajuda",
            "suporte",
            "alterar meu endereco",
            "mudar meu endereco",
            "trocar meu endereco",
        )

        if any(term in text for term in immediate_terms):
            return True

        if "?" in text:
            return True

        starters = (
            "tem ",
            "voces ",
            "aceita ",
            "entrega ",
            "qual ",
            "como ",
            "onde ",
            "quando ",
            "quanto ",
            "posso ",
            "horario",
            "preco ",
            "valor ",
            "taxa ",
            "frete ",
        )

        return text.startswith(starters)

    def _is_order_collection_human_request(
        self,
        value: str,
    ) -> bool:
        text = self._normalize_order_collection_text(value)

        return any(
            term in text
            for term in (
                "atendente",
                "falar com humano",
                "falar com uma pessoa",
                "falar com alguem",
                "atendimento humano",
                "falar com gerente",
                "falar com o gerente",
                "falar com responsavel",
                "falar com o responsavel",
            )
        )

    def _is_order_collection_cancel(
        self,
        value: str,
    ) -> bool:
        text = self._normalize_order_collection_text(value)

        return any(
            term in text
            for term in (
                "cancelar",
                "cancela",
                "nao quero mais",
                "deixa pra la",
                "desisto",
            )
        )

    def _resolve_customer(self, db: Session, *, store_id: Any, phone: str, profile_name: str | None) -> Customer:
        customer = db.scalar(select(Customer).where(Customer.store_id == store_id, Customer.phone == phone))
        clean_name = (profile_name or "").strip()
        if customer is not None:
            changed = False
            if not customer.active:
                customer.active = True
                changed = True
            if clean_name and customer.name.startswith("Cliente WhatsApp ") and customer.name != clean_name:
                customer.name = clean_name[:160]
                changed = True
            if changed:
                db.commit()
                db.refresh(customer)
            return customer
        name = clean_name[:160] if len(clean_name) >= 2 else f"Cliente WhatsApp {phone[-4:]}"
        customer = Customer(store_id=store_id, name=name, phone=phone, active=True)
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer

    def _store_conversation_media(
        self,
        *,
        account: ChannelAccount,
        conversation,
        media_id: str,
        message_type: str,
        filename: str | None,
    ) -> dict[str, Any]:
        """
        Baixa e persiste uma copia da midia para uso da Central Web.

        Falha de armazenamento nunca deve impedir o atendimento humano.
        """
        base = {
            "media_id": media_id,
            "media_type": message_type,
            "filename": filename,
        }

        if self.client_factory is None:
            return {
                **base,
                "stored_media": False,
                "storage_error": "WHATSAPP_CLIENT_UNAVAILABLE",
            }

        try:
            downloaded = self.client_factory().download_media(
                phone_number_id=account.external_account_id,
                media_id=media_id,
            )

            stored = self.conversation_media.store(
                store_id=account.store_id,
                conversation_id=conversation.id,
                content=downloaded.content,
                mime_type=downloaded.mime_type,
                original_filename=filename,
            )

            return {
                **base,
                "stored_media": True,
                "stored_media_path": stored.relative_path,
                "mime_type": stored.mime_type,
                "file_size": stored.file_size,
                "sha256": stored.sha256,
                "filename": (
                    stored.original_filename
                    or filename
                ),
            }

        except Exception as error:
            return {
                **base,
                "stored_media": False,
                "storage_error": type(error).__name__,
            }

    def _route_human_only(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        event: ChannelEvent,
        conversation,
        sender: str,
        content: str,
        content_type: str = "TEXT",
        metadata_json: dict[str, Any] | None = None,
        reason: str = "Atendimento em modo 100% humano",
    ) -> None:
        """Encaminha cliente para humano sem executar Olivia/OpenAI."""

        self.conversations.add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content_type=content_type,
                content=content,
                external_message_id=event.external_event_id,
                metadata_json=metadata_json,
            ),
        )

        # Se ja estiver aguardando, apenas registra a nova mensagem.
        if conversation.status == "WAITING_HUMAN":
            return

        ticket = self.conversations.create_ticket(
            db,
            store_id=account.store_id,
            payload=HumanTicketCreate(
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                category="OTHER",
                priority="URGENT",
                reason=reason,
                customer_message=content,
            ),
        )

        self.conversations.wait_for_human(
            db,
            conversation_id=conversation.id,
            reason=reason,
            ticket_id=ticket.id,
        )

        self.human_relay.notify_waiting(
            db,
            store_id=account.store_id,
            conversation_id=conversation.id,
            reason=reason,
        )

        self.repository.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=sender,
            content=(
                "Recebi sua mensagem. Nosso atendimento esta sendo "
                "feito por uma atendente e encaminhei sua conversa "
                "para ela. Nao precisa repetir a mensagem."
            ),
        )

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

                contacts_by_phone: dict[str, str] = {}
                for contact in value.get("contacts", []) or []:
                    contact_phone = normalize_whatsapp_recipient(str(contact.get("wa_id") or ""))
                    profile_name = str((contact.get("profile") or {}).get("name") or "").strip()
                    if contact_phone and profile_name:
                        contacts_by_phone[contact_phone] = profile_name

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
                    message_payload = dict(message)
                    contact_phone = normalize_whatsapp_recipient(str(message.get("from") or ""))
                    profile_name = contacts_by_phone.get(contact_phone)
                    if profile_name:
                        message_payload["_contact_profile_name"] = profile_name

                    event = self.repository.create_event(
                        db,
                        account=account,
                        external_event_id=external_message_id,
                        event_type="INBOUND_MESSAGE",
                        payload=message_payload,
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
        profile_name = str(message.get("_contact_profile_name") or "").strip() or None

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

            customer = self._resolve_customer(
                db,
                store_id=account.store_id,
                phone=sender,
                profile_name=profile_name,
            )

            conversation = self.conversations.get_or_create(
                db,
                ConversationCreate(
                    store_id=account.store_id,
                    customer_id=customer.id,
                    channel="WHATSAPP",
                    external_conversation_id=sender,
                ),
            )

            # MODO 100% HUMANO: imagem/documento não passa pelo analisador PIX/OpenAI.
            if (
                is_store_human_only(db, store_id=account.store_id)
                and conversation.status != "HUMAN"
            ):
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

                self._route_human_only(
                    db,
                    account=account,
                    event=event,
                    conversation=conversation,
                    sender=sender,
                    content=history_content,
                    content_type=message_type.upper(),
                    metadata_json={
                        **self._store_conversation_media(
                            account=account,
                            conversation=conversation,
                            media_id=media_id,
                            message_type=message_type,
                            filename=filename,
                        ),
                        "caption": caption,
                        "human_only_mode": True,
                    },
                )
                return

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

                try:
                    self.human_relay.forward_customer_media_to_staff(
                        db,
                        account=account,
                        conversation=conversation,
                        media_id=media_id,
                        media_type=message_type,
                        filename=filename,
                        caption=caption,
                    )
                except Exception:
                    pass

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
                            **self._store_conversation_media(
                                account=account,
                                conversation=conversation,
                                media_id=media_id,
                                message_type=message_type,
                                filename=filename,
                            ),
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

        customer = self._resolve_customer(
            db,
            store_id=account.store_id,
            phone=sender,
            profile_name=profile_name,
        )

        conversation = self.conversations.get_or_create(
            db,
            ConversationCreate(
                store_id=account.store_id,
                customer_id=customer.id,
                channel="WHATSAPP",
                external_conversation_id=sender,
            ),
        )

        # MODO 100% HUMANO: texto, botão e localização não chegam à OpenAI.
        if (
            is_store_human_only(db, store_id=account.store_id)
            and conversation.status != "HUMAN"
        ):
            self._route_human_only(
                db,
                account=account,
                event=event,
                conversation=conversation,
                sender=sender,
                content=body,
            )
            return

        # Localização compartilhada pelo WhatsApp fica exclusivamente
        # com o atendimento humano e nunca é enviada à Olivia/OpenAI.
        if (
            message_type == "location"
            and conversation.status == "OPEN"
        ):
            self._route_human_only(
                db,
                account=account,
                event=event,
                conversation=conversation,
                sender=sender,
                content=body,
                content_type="LOCATION",
                reason="Localização compartilhada pelo cliente",
            )
            return

        # Pedido já passou pelo checkout e continua ativo:
        # a Olivia não pode mais alterar o pedido enviado à operação/Consumer.
        # Encaminha diretamente ao humano sem executar OpenAI.
        if conversation.status == "OPEN":
            active_order = self.orders.get_latest_active_for_customer(
                db,
                store_id=account.store_id,
                customer_id=customer.id,
            )
            collection_in_progress = (
                self._order_collection_state(
                    db,
                    conversation_id=conversation.id,
                )
                != "NORMAL"
            )

            if (
                active_order is not None
                and self._active_order_blocks_olivia(
                    db,
                    store_id=account.store_id,
                    order=active_order,
                )
                and not collection_in_progress
                and not self._is_explicit_new_order_request(body)
            ):
                self._route_human_only(
                    db,
                    account=account,
                    event=event,
                    conversation=conversation,
                    sender=sender,
                    content=body,
                    reason=(
                        f"Pedido #{active_order.display_id} ativo após checkout — "
                        "intervenção humana necessária"
                    ),
                )
                return

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

        # CLOSED_STORE_ZERO_GPT
        if (
            conversation.status == "OPEN"
            and self._handle_closed_store_contact(
                db,
                account=account,
                conversation=conversation,
                event=event,
                recipient=sender,
                content=body,
            )
        ):
            return

        olivia_extra_instructions = None
        olivia_excluded_tools = None

        # ORDER_COLLECTION_COST_OPTIMIZATION
        # Camada deterministica anterior a Olivia/OpenAI.
        # Preserva todas as capacidades da Olivia e apenas reduz
        # chamadas intermediarias enquanto o cliente monta o pedido.
        collection_state = self._order_collection_state(
            db,
            conversation_id=conversation.id,
        )

        if (
            conversation.status == "OPEN"
            and collection_state == "COLLECTING_ORDER"
        ):
            if self._is_order_collection_human_request(body):
                self._set_order_collection_state(
                    db,
                    store_id=account.store_id,
                    conversation_id=conversation.id,
                    state="NORMAL",
                    reason="human_request",
                )
                self._route_human_only(
                    db,
                    account=account,
                    event=event,
                    conversation=conversation,
                    sender=sender,
                    content=body,
                    reason=(
                        "Cliente pediu atendimento humano "
                        "durante a coleta do pedido"
                    ),
                )
                return

            if self._is_order_collection_cancel(body):
                self._save_order_collection_customer_message(
                    db,
                    conversation_id=conversation.id,
                    event=event,
                    content=body,
                )
                self._set_order_collection_state(
                    db,
                    store_id=account.store_id,
                    conversation_id=conversation.id,
                    state="NORMAL",
                    reason="customer_cancelled_collection",
                )
                self._send_order_collection_message(
                    db,
                    account=account,
                    conversation=conversation,
                    recipient=sender,
                    content=(
                        "Tudo bem. Interrompi a montagem desse pedido. "
                        "Se quiser começar outro, é só me avisar."
                    ),
                    prompt_type="ORDER_COLLECTION_CANCELLED",
                )
                return

            if self._is_order_collection_wait_time_question(body):
                self._save_order_collection_customer_message(
                    db,
                    conversation_id=conversation.id,
                    event=event,
                    content=body,
                )

                prep_minutes = (
                    self._order_collection_average_prep_minutes(
                        db,
                        store_id=account.store_id,
                    )
                )

                if prep_minutes is not None:
                    prep_message = (
                        "Nosso tempo médio de preparo é de cerca de "
                        f"{prep_minutes} minutos 👍 "
                        "Pode continuar me enviando os itens. "
                        "Quando terminar, diga 'só isso' ou "
                        "'já pode montar'."
                    )
                else:
                    prep_message = (
                        "O tempo de preparo pode variar conforme "
                        "o movimento 👍 "
                        "Pode continuar me enviando os itens. "
                        "Quando terminar, diga 'só isso' ou "
                        "'já pode montar'."
                    )

                self._send_order_collection_message(
                    db,
                    account=account,
                    conversation=conversation,
                    recipient=sender,
                    content=prep_message,
                    prompt_type="ORDER_COLLECTION_PREP_TIME",
                )
                return

            if self._is_order_collection_general_question(body):
                olivia_extra_instructions = (
                    "CONTEXTO TEMPORARIO DE COLETA DE PEDIDO: "
                    "responda somente a duvida atual do cliente. "
                    "Os itens anteriores ainda estao sendo coletados e "
                    "nao devem ser adicionados, removidos, alterados, "
                    "confirmados ou finalizados agora. "
                    "Depois de responder, aguarde o cliente continuar."
                )

                olivia_excluded_tools = {
                    "get_or_create_cart",
                    "add_cart_item",
                    "update_cart_item",
                    "remove_cart_item",
                    "checkout_cart",
                }

            else:
                if self._is_order_collection_finish_trigger(body):
                    # A pergunta "mais alguma coisa?" ja foi feita
                    # deterministicamente apos o ultimo item.
                    # Agora libera a Olivia uma unica vez para montar
                    # todo o historico acumulado.
                    self._set_order_collection_state(
                        db,
                        store_id=account.store_id,
                        conversation_id=conversation.id,
                        state="NORMAL",
                        reason="customer_ready_to_mount",
                    )
                else:
                    self._save_order_collection_customer_message(
                        db,
                        conversation_id=conversation.id,
                        event=event,
                        content=body,
                    )
                    self._send_order_collection_message(
                        db,
                        account=account,
                        conversation=conversation,
                        recipient=sender,
                        content=(
                            "Anotei 👍 Mais alguma coisa ou "
                            "ja posso montar seu pedido?"
                        ),
                        prompt_type="ORDER_COLLECTION_ITEM_ACK",
                    )
                    return

        if (
            conversation.status == "OPEN"
            and collection_state == "AWAITING_EXTRA"
        ):
            if self._is_order_collection_human_request(body):
                self._set_order_collection_state(
                    db,
                    store_id=account.store_id,
                    conversation_id=conversation.id,
                    state="NORMAL",
                    reason="human_request_while_awaiting_extra",
                )
                self._route_human_only(
                    db,
                    account=account,
                    event=event,
                    conversation=conversation,
                    sender=sender,
                    content=body,
                    reason=(
                        "Cliente pediu atendimento humano "
                        "antes da confirmacao do pedido"
                    ),
                )
                return

            if self._is_order_collection_cancel(body):
                self._save_order_collection_customer_message(
                    db,
                    conversation_id=conversation.id,
                    event=event,
                    content=body,
                )
                self._set_order_collection_state(
                    db,
                    store_id=account.store_id,
                    conversation_id=conversation.id,
                    state="NORMAL",
                    reason="customer_cancelled_while_awaiting_extra",
                )
                self._send_order_collection_message(
                    db,
                    account=account,
                    conversation=conversation,
                    recipient=sender,
                    content=(
                        "Tudo bem. Interrompi a montagem desse pedido. "
                        "Se quiser começar outro, é só me avisar."
                    ),
                    prompt_type="ORDER_COLLECTION_CANCELLED",
                )
                return

            # Esta e a resposta para a pergunta de adicional.
            # Agora liberamos a Olivia uma unica vez para interpretar
            # todo o historico acumulado e continuar normalmente.
            self._set_order_collection_state(
                db,
                store_id=account.store_id,
                conversation_id=conversation.id,
                state="NORMAL",
                reason="extra_answer_received_release_to_olivia",
            )

        elif (
            conversation.status == "OPEN"
            and collection_state == "NORMAL"
            and self._is_order_collection_start(body)
        ):
            self._save_order_collection_customer_message(
                db,
                conversation_id=conversation.id,
                event=event,
                content=body,
            )
            if self._is_order_collection_finish_trigger(body):
                self._set_order_collection_state(
                    db,
                    store_id=account.store_id,
                    conversation_id=conversation.id,
                    state="AWAITING_EXTRA",
                    reason="order_intent_with_finish_trigger",
                )
                self._send_order_collection_message(
                    db,
                    account=account,
                    conversation=conversation,
                    recipient=sender,
                    content=(
                        "Certo. Antes de fechar, deseja acrescentar "
                        "mais alguma coisa ou algum adicional ao pedido?"
                    ),
                    prompt_type="ORDER_COLLECTION_EXTRA_PROMPT",
                )
            else:
                self._set_order_collection_state(
                    db,
                    store_id=account.store_id,
                    conversation_id=conversation.id,
                    state="COLLECTING_ORDER",
                    reason="explicit_order_intent",
                )
                self._send_order_collection_message(
                    db,
                    account=account,
                    conversation=conversation,
                    recipient=sender,
                    content=(
                        "Pode me mandar seu pedido completo. "
                        "Pode enviar os itens em mensagens separadas. "
                        "Quando terminar, diga que é só isso ou pergunte o valor."
                    ),
                    prompt_type="ORDER_COLLECTION_START",
                )

            return

        try:
            reply = self.orchestrator_factory().reply(
                db,
                store_id=account.store_id,
                conversation_id=conversation.id,
                customer_message=body,
                customer_phone=sender,
                extra_instructions=olivia_extra_instructions,
                excluded_tools=olivia_excluded_tools,
            )

        except OpenAIProviderRequestError as error:
            # Nunca deixa o cliente sem resposta por falha da OpenAI.
            self.conversations.record_event(
                db,
                store_id=account.store_id,
                payload=AIEventCreate(
                    conversation_id=conversation.id,
                    event_type="AI_PROVIDER_FAILURE",
                    success=False,
                    payload_json={
                        "provider": "OPENAI",
                        "fallback": "HUMAN_HANDOFF",
                    },
                    error_message=str(error),
                ),
            )

            ticket = self.conversations.create_ticket(
                db,
                store_id=account.store_id,
                payload=HumanTicketCreate(
                    conversation_id=conversation.id,
                    customer_id=conversation.customer_id,
                    category="OTHER",
                    priority="URGENT",
                    reason=(
                        "Instabilidade temporária do provedor "
                        "de IA/OpenAI"
                    ),
                    customer_message=body,
                ),
            )

            self.conversations.wait_for_human(
                db,
                conversation_id=conversation.id,
                reason=(
                    "Atendimento automático temporariamente "
                    "indisponível"
                ),
                ticket_id=ticket.id,
            )

            self.human_relay.notify_waiting(
                db,
                store_id=account.store_id,
                conversation_id=conversation.id,
                reason=(
                    "Atendimento automático temporariamente "
                    "indisponível"
                ),
            )

            self.repository.create_outbound(
                db,
                account=account,
                conversation_id=conversation.id,
                recipient=sender,
                content=(
                    "Recebi sua mensagem. Estamos com uma "
                    "instabilidade temporária no atendimento "
                    "automático e encaminhei sua conversa para "
                    "atendimento humano. Não precisa repetir "
                    "a mensagem."
                ),
            )
            return

        self.repository.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=sender,
            content=sanitize_whatsapp_text(reply),
        )
