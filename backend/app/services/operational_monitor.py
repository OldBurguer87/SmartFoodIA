from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage
from app.models.conversation import HumanTicket
from app.models.integration import StoreIntegration
from app.services.commercial_status import CommercialStatusService
from app.services.manager_escalation import ManagerEscalationService


logger = logging.getLogger("smartfoodia.operational-monitor")


class OperationalMonitorService:
    WINDOW_MINUTES = 15
    CONSUMER_WARNING_SECONDS = 120
    CONSUMER_CRITICAL_SECONDS = 300
    STORE_OPEN_GRACE_SECONDS = 900
    PREFIX = "[AUTO-MONITOR]"

    def __init__(self) -> None:
        self.manager = ManagerEscalationService()

    def run(self, db: Session) -> dict[str, int]:
        opened = resolved = checked = 0
        stores = list(db.scalars(select(Store)).all())
        for store in stores:
            checked += 1
            checks = self._checks(db, store.id)
            for code, failure in checks.items():
                if failure:
                    if self._open_ticket(db, store.id, code, failure):
                        opened += 1

                        # O alerta ao gerente representa um novo incidente.
                        # Se a falha persistir, o ticket existente impede
                        # notificações repetidas em cada ciclo do monitor.
                        try:
                            self.manager.notify_system(
                                db,
                                store_id=store.id,
                                title=f"Falha crítica: {code}",
                                details=failure,
                                source=(
                                    f"OPERATIONAL_MONITOR_{code}"
                                ),
                            )
                        except Exception:
                            # A falha de notificação nunca pode impedir
                            # o monitor de registrar o incidente.
                            logger.exception(
                                "Falha ao notificar gerente sobre "
                                "incidente operacional %s da loja %s",
                                code,
                                store.id,
                            )
                else:
                    resolved += self._resolve_ticket(db, store.id, code)
        return {"stores_checked": checked, "tickets_opened": opened, "tickets_resolved": resolved}

    def _checks(self, db: Session, store_id) -> dict[str, str | None]:
        now = datetime.now(timezone.utc)
        recent = now - timedelta(minutes=self.WINDOW_MINUTES)
        account_ids = select(ChannelAccount.id).where(ChannelAccount.store_id == store_id)

        openai = db.scalar(
            select(ChannelEvent).where(
                ChannelEvent.channel_account_id.in_(account_ids),
                ChannelEvent.updated_at >= recent,
                ChannelEvent.status.in_(["RETRY", "DEAD", "FAILED"]),
                ChannelEvent.error_message.ilike("%OpenAI:%"),
            ).order_by(ChannelEvent.updated_at.desc())
        )

        whatsapp_outbound = db.scalar(
            select(OutboundChannelMessage).where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.updated_at >= recent,
                OutboundChannelMessage.status.in_(["RETRY", "DEAD"]),
            ).order_by(OutboundChannelMessage.updated_at.desc())
        )

        status_payloads = list(db.scalars(
            select(ChannelEvent.payload_json).where(
                ChannelEvent.channel_account_id.in_(account_ids),
                ChannelEvent.event_type == "MESSAGE_STATUS",
                ChannelEvent.created_at >= recent,
            )
        ).all())
        delivery_failed = any(
            isinstance(payload, dict) and payload.get("status") == "failed"
            for payload in status_payloads
        )

        consumer_integration = db.scalar(
            select(StoreIntegration).where(
                StoreIntegration.store_id == store_id,
                StoreIntegration.provider == "CONSUMER",
            )
        )
        consumer_failure = None

        if consumer_integration is None or not consumer_integration.active:
            consumer_failure = "Integração Consumer ausente ou inativa."
        else:
            monitoring = CommercialStatusService().monitoring_status(
                db,
                store_id,
            )

            if monitoring["should_monitor"]:
                opened_at = monitoring.get("opened_at")
                local_time = monitoring.get("local_time")

                in_opening_grace = False
                if opened_at is not None and local_time is not None:
                    seconds_since_open = max(
                        0,
                        int(
                            (
                                local_time - opened_at
                            ).total_seconds()
                        ),
                    )
                    in_opening_grace = (
                        seconds_since_open
                        < self.STORE_OPEN_GRACE_SECONDS
                    )

                if not in_opening_grace:
                    age = max(
                        0,
                        int(
                            (
                                now - consumer_integration.updated_at
                            ).total_seconds()
                        ),
                    )

                    if age > self.CONSUMER_CRITICAL_SECONDS:
                        consumer_failure = (
                            f"Consumer sem polling há "
                            f"{age // 60} minuto(s)."
                        )

        queue_problem_count = db.scalar(
            select(func.count(ChannelEvent.id)).where(
                ChannelEvent.channel_account_id.in_(account_ids),
                ChannelEvent.updated_at >= recent,
                ChannelEvent.status.in_(["RETRY", "DEAD"]),
            )
        ) or 0
        queue_problem_count += db.scalar(
            select(func.count(OutboundChannelMessage.id)).where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.updated_at >= recent,
                OutboundChannelMessage.status.in_(["RETRY", "DEAD"]),
            )
        ) or 0

        return {
            "OPENAI": f"OpenAI com falha recente: {openai.error_message[:300]}" if openai else None,
            "WHATSAPP": (
                "WhatsApp/Meta com falha recente de envio ou entrega."
                if whatsapp_outbound or delivery_failed else None
            ),
            "CONSUMER": consumer_failure,
            "QUEUE": (
                f"Fila operacional possui {queue_problem_count} item(ns) em RETRY/DEAD."
                if queue_problem_count else None
            ),
        }

    def _ticket_reason(self, code: str) -> str:
        return f"{self.PREFIX} {code}"

    def _open_ticket(self, db: Session, store_id, code: str, message: str) -> bool:
        reason = self._ticket_reason(code)
        existing = db.scalar(
            select(HumanTicket).where(
                HumanTicket.store_id == store_id,
                HumanTicket.reason == reason,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
            )
        )
        if existing:
            existing.customer_message = message
            existing.priority = "URGENT"
            db.commit()
            return False

        db.add(HumanTicket(
            store_id=store_id,
            category="SYSTEM",
            priority="URGENT",
            status="OPEN",
            reason=reason,
            customer_message=message,
        ))
        db.commit()
        return True

    def _resolve_ticket(self, db: Session, store_id, code: str) -> int:
        reason = self._ticket_reason(code)
        tickets = list(db.scalars(
            select(HumanTicket).where(
                HumanTicket.store_id == store_id,
                HumanTicket.reason == reason,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
            )
        ).all())
        if not tickets:
            return 0
        for ticket in tickets:
            ticket.status = "RESOLVED"
            ticket.resolution = "Resolvido automaticamente após recuperação do serviço."
            ticket.assigned_to = "system-monitor"
        db.commit()
        return len(tickets)
