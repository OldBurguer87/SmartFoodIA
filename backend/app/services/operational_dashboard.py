from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.channel import (
    ChannelAccount,
    ChannelEvent,
    OutboundChannelMessage,
)
from app.models.conversation import AIEvent, Conversation, HumanTicket, KnowledgeGap
from app.models.order import Order


class OperationalDashboardService:
    def overview(
        self,
        db: Session,
        *,
        store_id: UUID,
        hours: int = 24,
    ) -> dict:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        conversation_counts = self._grouped_count(
            db,
            select(Conversation.status, func.count(Conversation.id))
            .where(
                Conversation.store_id == store_id,
                Conversation.updated_at >= since,
            )
            .group_by(Conversation.status),
        )
        ticket_counts = self._grouped_count(
            db,
            select(HumanTicket.status, func.count(HumanTicket.id))
            .where(
                HumanTicket.store_id == store_id,
                HumanTicket.updated_at >= since,
            )
            .group_by(HumanTicket.status),
        )
        order_counts = self._grouped_count(
            db,
            select(Order.status, func.count(Order.id))
            .where(
                Order.store_id == store_id,
                Order.created_at >= since,
            )
            .group_by(Order.status),
        )

        order_summary = db.execute(
            select(
                func.count(Order.id),
                func.coalesce(func.sum(Order.total), 0),
            ).where(
                Order.store_id == store_id,
                Order.created_at >= since,
            )
        ).one()

        ai_summary = db.execute(
            select(
                func.count(AIEvent.id),
                func.coalesce(
                    func.sum(
                        func.cast(AIEvent.success.is_(False), IntegerCompat)
                    ),
                    0,
                ),
                func.coalesce(func.avg(AIEvent.duration_ms), 0),
            ).where(
                AIEvent.store_id == store_id,
                AIEvent.created_at >= since,
            )
        ).one()

        queue = self._queue_summary(db, store_id=store_id)
        open_gaps = db.scalar(
            select(func.count(KnowledgeGap.id)).where(
                KnowledgeGap.store_id == store_id,
                KnowledgeGap.status == "OPEN",
            )
        ) or 0
        urgent_tickets = db.scalar(
            select(func.count(HumanTicket.id)).where(
                HumanTicket.store_id == store_id,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
                HumanTicket.priority == "URGENT",
            )
        ) or 0

        alerts = []
        if queue["events_dead"] or queue["outbound_dead"]:
            alerts.append({
                "severity": "CRITICAL",
                "code": "DEAD_QUEUE_ITEMS",
                "message": (
                    "Existem mensagens que atingiram o limite de tentativas."
                ),
            })
        if queue["events_retry"] or queue["outbound_retry"]:
            alerts.append({
                "severity": "WARNING",
                "code": "QUEUE_RETRIES",
                "message": "Existem mensagens aguardando nova tentativa.",
            })
        if urgent_tickets:
            alerts.append({
                "severity": "CRITICAL",
                "code": "URGENT_TICKETS",
                "message": f"Existem {urgent_tickets} ticket(s) urgente(s).",
            })
        if open_gaps:
            alerts.append({
                "severity": "INFO",
                "code": "OPEN_KNOWLEDGE_GAPS",
                "message": (
                    f"Existem {open_gaps} lacuna(s) de conhecimento aberta(s)."
                ),
            })

        return {
            "store_id": str(store_id),
            "period_hours": hours,
            "generated_at": datetime.now(timezone.utc),
            "conversations": {
                "total": sum(conversation_counts.values()),
                "open": conversation_counts.get("OPEN", 0),
                "human": conversation_counts.get("HUMAN", 0),
                "closed": conversation_counts.get("CLOSED", 0),
            },
            "tickets": {
                "total": sum(ticket_counts.values()),
                "open": ticket_counts.get("OPEN", 0),
                "in_progress": ticket_counts.get("IN_PROGRESS", 0),
                "resolved": ticket_counts.get("RESOLVED", 0),
                "urgent_active": urgent_tickets,
            },
            "orders": {
                "total": int(order_summary[0] or 0),
                "revenue": float(Decimal(order_summary[1] or 0)),
                "by_status": order_counts,
            },
            "ai": {
                "events": int(ai_summary[0] or 0),
                "errors": int(ai_summary[1] or 0),
                "average_duration_ms": round(float(ai_summary[2] or 0), 2),
            },
            "queue": queue,
            "knowledge": {
                "open_gaps": open_gaps,
            },
            "alerts": alerts,
        }

    @staticmethod
    def _grouped_count(db: Session, statement) -> dict[str, int]:
        return {
            str(status): int(count)
            for status, count in db.execute(statement).all()
        }

    @staticmethod
    def _queue_summary(db: Session, *, store_id: UUID) -> dict[str, int]:
        account_ids = select(ChannelAccount.id).where(
            ChannelAccount.store_id == store_id
        )
        event_counts = {
            str(status): int(count)
            for status, count in db.execute(
                select(ChannelEvent.status, func.count(ChannelEvent.id))
                .where(ChannelEvent.channel_account_id.in_(account_ids))
                .group_by(ChannelEvent.status)
            ).all()
        }
        outbound_counts = {
            str(status): int(count)
            for status, count in db.execute(
                select(
                    OutboundChannelMessage.status,
                    func.count(OutboundChannelMessage.id),
                )
                .where(
                    OutboundChannelMessage.channel_account_id.in_(account_ids)
                )
                .group_by(OutboundChannelMessage.status)
            ).all()
        }
        return {
            "events_received": event_counts.get("RECEIVED", 0),
            "events_retry": event_counts.get("RETRY", 0),
            "events_dead": event_counts.get("DEAD", 0),
            "events_processed": event_counts.get("PROCESSED", 0),
            "outbound_pending": outbound_counts.get("PENDING", 0),
            "outbound_retry": outbound_counts.get("RETRY", 0),
            "outbound_dead": outbound_counts.get("DEAD", 0),
            "outbound_sent": outbound_counts.get("SENT", 0),
        }


# SQLite and PostgreSQL both accept INTEGER in CAST expressions.
from sqlalchemy import Integer as IntegerCompat  # noqa: E402
