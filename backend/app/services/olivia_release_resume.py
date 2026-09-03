from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.openai_provider import (
    OpenAIProviderRequestError,
    OpenAIResponsesProvider,
)
from app.models.conversation import (
    AIEvent,
    Conversation,
    Message,
)
from app.repositories.channel import ChannelRepository
from app.schemas.conversation import (
    AIEventCreate,
    HumanTicketCreate,
)
from app.services.conversation import ConversationService
from app.services.human_relay import HumanRelayService


logger = logging.getLogger(
    "smartfoodia.olivia-release-resume"
)


class OliviaReleaseResumeService:
    def __init__(
        self,
        *,
        orchestrator_factory: Callable | None = None,
    ) -> None:
        self.orchestrator_factory = (
            orchestrator_factory
            or (
                lambda: OliviaOrchestrator(
                    OpenAIResponsesProvider()
                )
            )
        )
        self.conversations = ConversationService()
        self.channels = ChannelRepository()
        self.relay = HumanRelayService()

    def _pending_customer_message(
        self,
        db: Session,
        *,
        conversation_id,
    ) -> Message | None:
        # A retomada roda logo após HUMAN_RELEASE.
        # Primeiro identifica exatamente esse ciclo humano.
        current_release = db.scalar(
            select(AIEvent)
            .where(
                AIEvent.conversation_id
                == conversation_id,
                AIEvent.event_type == "HUMAN_RELEASE",
            )
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        if current_release is None:
            return None

        takeover = db.scalar(
            select(AIEvent)
            .where(
                AIEvent.conversation_id
                == conversation_id,
                AIEvent.event_type == "HUMAN_TAKEOVER",
                AIEvent.created_at
                <= current_release.created_at,
            )
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        if takeover is None:
            return None

        # Descobre o release anterior para não misturar
        # ciclos humanos diferentes.
        previous_release = db.scalar(
            select(AIEvent)
            .where(
                AIEvent.conversation_id
                == conversation_id,
                AIEvent.event_type == "HUMAN_RELEASE",
                AIEvent.created_at < takeover.created_at,
            )
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        waiting_conditions = [
            AIEvent.conversation_id == conversation_id,
            AIEvent.event_type == "HUMAN_WAITING",
            AIEvent.created_at <= takeover.created_at,
        ]

        if previous_release is not None:
            waiting_conditions.append(
                AIEvent.created_at
                > previous_release.created_at
            )

        waiting = db.scalar(
            select(AIEvent)
            .where(*waiting_conditions)
            .order_by(AIEvent.created_at.desc())
            .limit(1)
        )

        # No incidente do 429, a mensagem chegou enquanto
        # estava WAITING_HUMAN, antes do takeover.
        cycle_start = (
            waiting.created_at
            if waiting is not None
            else takeover.created_at
        )

        # Limita também o fim ao release atual.
        # Mensagem nova posterior ao release deve seguir
        # pelo gateway normal, não por este replay.
        inbound = db.scalar(
            select(Message)
            .where(
                Message.conversation_id
                == conversation_id,
                Message.direction == "INBOUND",
                Message.sender_type == "CUSTOMER",
                Message.created_at >= cycle_start,
                Message.created_at
                <= current_release.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )

        if inbound is None:
            return None

        human_reply = db.scalar(
            select(Message)
            .where(
                Message.conversation_id
                == conversation_id,
                Message.direction == "OUTBOUND",
                Message.sender_type == "HUMAN",
                Message.created_at >= cycle_start,
                Message.created_at
                <= current_release.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )

        if (
            human_reply is not None
            and human_reply.created_at
            >= inbound.created_at
        ):
            return None

        return inbound

    def resume_if_needed(
        self,
        db: Session,
        *,
        conversation: Conversation,
    ) -> bool:
        if conversation.status != "OPEN":
            return False

        pending = self._pending_customer_message(
            db,
            conversation_id=conversation.id,
        )

        if pending is None:
            return False

        conversation.status = "RESUMING_OLIVIA"
        db.commit()
        db.refresh(conversation)

        try:
            reply = self.orchestrator_factory().reply(
                db,
                store_id=conversation.store_id,
                conversation_id=conversation.id,
                customer_message="",
                customer_phone=(
                    conversation.external_conversation_id
                    or ""
                ),
                record_customer_message=False,
                extra_instructions=(
                    "RETOMADA APÓS ATENDIMENTO HUMANO: "
                    "existe mensagem do cliente posterior "
                    "à última resposta enviada. Continue "
                    "a partir de todo o histórico e responda "
                    "diretamente ao que ficou pendente. "
                    "Não peça para repetir a mensagem."
                ),
                excluded_tools={
                    "request_human_help",
                    "report_order_issue",
                },
            )
        except Exception as error:
            self._handle_failure(
                db,
                conversation=conversation,
                pending=pending,
                error=error,
            )
            return False

        latest = db.get(
            Conversation,
            conversation.id,
        )

        if (
            latest is None
            or latest.status != "RESUMING_OLIVIA"
        ):
            return False

        latest.status = "OPEN"

        db.add(
            AIEvent(
                store_id=latest.store_id,
                conversation_id=latest.id,
                event_type="HUMAN_RELEASE_RESUMED",
                success=True,
                payload_json={
                    "pending_message_id": str(pending.id),
                },
            )
        )
        db.commit()
        db.refresh(latest)

        account = self.channels.get_account_by_store(
            db,
            store_id=latest.store_id,
            provider="WHATSAPP_CLOUD",
        )

        if (
            account is not None
            and latest.external_conversation_id
            and str(reply or "").strip()
        ):
            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=latest.id,
                recipient=latest.external_conversation_id,
                content=str(reply).strip(),
            )

        return True

    def _handle_failure(
        self,
        db: Session,
        *,
        conversation: Conversation,
        pending: Message,
        error: Exception,
    ) -> None:
        latest = db.get(
            Conversation,
            conversation.id,
        )

        if latest is None:
            return

        event_type = (
            "AI_PROVIDER_FAILURE"
            if isinstance(
                error,
                OpenAIProviderRequestError,
            )
            else "HUMAN_RELEASE_RESUME_FAILURE"
        )

        self.conversations.record_event(
            db,
            store_id=latest.store_id,
            payload=AIEventCreate(
                conversation_id=latest.id,
                event_type=event_type,
                success=False,
                payload_json={
                    "source": "HUMAN_RELEASE_RESUME",
                },
                error_message=str(error),
            ),
        )

        ticket = self.conversations.create_ticket(
            db,
            store_id=latest.store_id,
            payload=HumanTicketCreate(
                conversation_id=latest.id,
                customer_id=latest.customer_id,
                category="OTHER",
                priority="URGENT",
                reason=(
                    "Falha ao retomar atendimento "
                    "com a Olívia"
                ),
                customer_message=pending.content,
            ),
        )

        self.conversations.wait_for_human(
            db,
            conversation_id=latest.id,
            reason=(
                "A Olívia não conseguiu retomar "
                "a conversa automaticamente"
            ),
            ticket_id=ticket.id,
        )

        try:
            self.relay.notify_waiting(
                db,
                store_id=latest.store_id,
                conversation_id=latest.id,
                reason=(
                    "Falha na retomada automática "
                    "da Olívia"
                ),
            )
        except Exception:
            logger.exception(
                "Falha ao avisar equipe sobre "
                "retomada da conversa %s",
                latest.id,
            )
