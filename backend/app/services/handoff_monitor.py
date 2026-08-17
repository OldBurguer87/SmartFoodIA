from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.openai_provider import OpenAIResponsesProvider
from app.core.config import settings
from app.models.conversation import AIEvent, Conversation
from app.repositories.channel import ChannelRepository
from app.services.human_relay import HumanRelayService


logger = logging.getLogger("smartfoodia.handoff-monitor")


@dataclass(frozen=True)
class HandoffMonitorResult:
    reminded: int = 0
    resumed: int = 0
    failed: int = 0


class HumanHandoffMonitor:
    def __init__(
        self,
        *,
        orchestrator_factory: Callable[[], OliviaOrchestrator] | None = None,
    ) -> None:
        self.channels = ChannelRepository()
        self.relay = HumanRelayService()
        self.orchestrator_factory = orchestrator_factory or (
            lambda: OliviaOrchestrator(OpenAIResponsesProvider())
        )

    def run_once(
        self,
        db: Session,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> HandoffMonitorResult:
        current_time = now or datetime.now(timezone.utc)
        reminded = resumed = failed = 0

        waiting = list(
            db.scalars(
                select(Conversation)
                .where(Conversation.status == "WAITING_HUMAN")
                .order_by(Conversation.last_message_at)
                .limit(limit)
            ).all()
        )

        for conversation in waiting:
            try:
                wait_event = db.scalar(
                    select(AIEvent)
                    .where(
                        AIEvent.conversation_id == conversation.id,
                        AIEvent.event_type == "HUMAN_WAITING",
                    )
                    .order_by(AIEvent.created_at.desc())
                    .limit(1)
                )

                if wait_event is None:
                    continue

                reason = str(
                    (wait_event.payload_json or {}).get("reason")
                    or "solicitação de atendimento"
                )

                staff_available = self.relay.staff_is_available_now(
                    db,
                    store_id=conversation.store_id,
                    now=current_time,
                )

                start_event = db.scalar(
                    select(AIEvent)
                    .where(
                        AIEvent.conversation_id == conversation.id,
                        AIEvent.event_type == "HUMAN_WAIT_STARTED",
                        AIEvent.created_at >= wait_event.created_at,
                    )
                    .order_by(AIEvent.created_at.desc())
                    .limit(1)
                )

                pause_event = db.scalar(
                    select(AIEvent)
                    .where(
                        AIEvent.conversation_id == conversation.id,
                        AIEvent.event_type == "HUMAN_WAIT_PAUSED",
                        AIEvent.created_at >= wait_event.created_at,
                    )
                    .order_by(AIEvent.created_at.desc())
                    .limit(1)
                )

                active_start = (
                    start_event is not None
                    and (
                        pause_event is None
                        or start_event.created_at > pause_event.created_at
                    )
                )

                if not staff_available:
                    if active_start:
                        db.add(
                            AIEvent(
                                store_id=conversation.store_id,
                                conversation_id=conversation.id,
                                event_type="HUMAN_WAIT_PAUSED",
                                success=True,
                                payload_json={
                                    "wait_event_id": str(wait_event.id),
                                    "start_event_id": str(start_event.id),
                                    "reason": reason,
                                },
                            )
                        )
                        db.commit()
                    continue

                if not active_start:
                    self.relay.notify_waiting(
                        db,
                        store_id=conversation.store_id,
                        conversation_id=conversation.id,
                        reason=reason,
                        reminder=False,
                        now=current_time,
                    )
                    continue

                age_seconds = (
                    current_time - start_event.created_at
                ).total_seconds()

                if age_seconds >= settings.human_wait_timeout_seconds:
                    if self._resume_with_olivia(
                        db,
                        conversation=conversation,
                        wait_event=wait_event,
                    ):
                        resumed += 1
                    continue

                if age_seconds >= settings.human_wait_reminder_seconds:
                    already_reminded = db.scalar(
                        select(AIEvent.id)
                        .where(
                            AIEvent.conversation_id == conversation.id,
                            AIEvent.event_type == "HUMAN_WAITING_REMINDER",
                            AIEvent.created_at >= start_event.created_at,
                        )
                        .limit(1)
                    )

                    if already_reminded is None:
                        reason = str(
                            (wait_event.payload_json or {}).get("reason")
                            or "solicitação de atendimento"
                        )
                        notified = self.relay.notify_waiting(
                            db,
                            store_id=conversation.store_id,
                            conversation_id=conversation.id,
                            reason=reason,
                            reminder=True,
                            now=current_time,
                        )

                        db.add(
                            AIEvent(
                                store_id=conversation.store_id,
                                conversation_id=conversation.id,
                                event_type="HUMAN_WAITING_REMINDER",
                                success=True,
                                payload_json={
                                    "notified": notified,
                                    "wait_event_id": str(wait_event.id),
                                },
                            )
                        )
                        db.commit()
                        reminded += 1

            except Exception:
                failed += 1
                logger.exception(
                    "Falha ao monitorar handoff da conversa %s",
                    conversation.id,
                )

        return HandoffMonitorResult(
            reminded=reminded,
            resumed=resumed,
            failed=failed,
        )

    def _resume_with_olivia(
        self,
        db: Session,
        *,
        conversation: Conversation,
        wait_event: AIEvent,
    ) -> bool:
        if conversation.status != "WAITING_HUMAN":
            return False

        reason = str(
            (wait_event.payload_json or {}).get("reason")
            or "solicitação de atendimento humano"
        )

        # Bloqueia uma tomada humana concorrente durante os poucos segundos
        # em que a Olívia prepara a resposta de retomada.
        conversation.status = "RESUMING_OLIVIA"
        db.commit()
        db.refresh(conversation)

        instructions = (
            "RETOMADA AUTOMÁTICA APÓS ESPERA POR ATENDIMENTO HUMANO: "
            "nenhum atendente conseguiu assumir dentro do tempo máximo. "
            f"Motivo original do encaminhamento: {reason}. "
            "Retome a conversa agora como Olívia e continue a partir de todo "
            "o histórico, inclusive mensagens que o cliente enviou enquanto "
            "aguardava. Avise brevemente que não conseguiu contato com alguém "
            "da equipe a tempo e que você voltou para continuar ajudando. "
            "Tente resolver por outra estratégia usando as ferramentas e os "
            "dados reais disponíveis. NÃO use request_human_help nem "
            "report_order_issue nesta rodada e não encaminhe novamente "
            "a conversa imediatamente. "
            "Não invente informação, prazo, estorno, desconto ou status. "
            "Se ainda não puder resolver com segurança, explique o limite de "
            "forma curta e faça no máximo uma pergunta útil para avançar."
        )

        try:
            reply = self.orchestrator_factory().reply(
                db,
                store_id=conversation.store_id,
                conversation_id=conversation.id,
                customer_message="",
                customer_phone=conversation.external_conversation_id,
                record_customer_message=False,
                extra_instructions=instructions,
                excluded_tools={
                    "request_human_help",
                    "report_order_issue",
                },
            )
        except Exception:
            latest = db.get(Conversation, conversation.id)
            if latest is not None and latest.status == "RESUMING_OLIVIA":
                latest.status = "WAITING_HUMAN"
                db.commit()
            raise

        latest = db.get(Conversation, conversation.id)
        if latest is None or latest.status != "RESUMING_OLIVIA":
            return False

        latest.status = "OPEN"
        db.add(
            AIEvent(
                store_id=latest.store_id,
                conversation_id=latest.id,
                event_type="HUMAN_WAIT_TIMEOUT",
                success=True,
                payload_json={
                    "wait_event_id": str(wait_event.id),
                    "reason": reason,
                    "resumed_by": "OLIVIA",
                },
            )
        )
        db.commit()

        account = self.channels.get_account_by_store(
            db,
            store_id=latest.store_id,
            provider="WHATSAPP_CLOUD",
        )

        if account is not None and latest.external_conversation_id:
            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=latest.id,
                recipient=latest.external_conversation_id,
                content=reply.strip(),
            )

        self.relay.notify_timeout(
            db,
            store_id=latest.store_id,
            conversation_id=latest.id,
        )

        return True
