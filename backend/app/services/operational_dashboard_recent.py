from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage
from app.services.operational_dashboard import OperationalDashboardService


class RecentOperationalDashboardService(OperationalDashboardService):
    """Dashboard view that keeps history but reports only recent queue failures as active."""

    ATTENTION_MINUTES = 15

    def overview(
        self,
        db: Session,
        *,
        store_id: UUID,
        hours: int = 24,
    ) -> dict:
        result = super().overview(db, store_id=store_id, hours=hours)
        now = datetime.now(timezone.utc)
        period_since = now - timedelta(hours=hours)
        attention_since = now - timedelta(minutes=self.ATTENTION_MINUTES)

        account_ids = select(ChannelAccount.id).where(
            ChannelAccount.store_id == store_id
        )

        event_period = self._counts(
            db,
            select(ChannelEvent.status, func.count(ChannelEvent.id))
            .where(
                ChannelEvent.channel_account_id.in_(account_ids),
                ChannelEvent.updated_at >= period_since,
            )
            .group_by(ChannelEvent.status),
        )
        outbound_period = self._counts(
            db,
            select(OutboundChannelMessage.status, func.count(OutboundChannelMessage.id))
            .where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.updated_at >= period_since,
            )
            .group_by(OutboundChannelMessage.status),
        )
        event_attention = self._counts(
            db,
            select(ChannelEvent.status, func.count(ChannelEvent.id))
            .where(
                ChannelEvent.channel_account_id.in_(account_ids),
                ChannelEvent.updated_at >= attention_since,
                ChannelEvent.status.in_(["RETRY", "DEAD"]),
            )
            .group_by(ChannelEvent.status),
        )
        outbound_attention = self._counts(
            db,
            select(OutboundChannelMessage.status, func.count(OutboundChannelMessage.id))
            .where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.updated_at >= attention_since,
                OutboundChannelMessage.status.in_(["RETRY", "DEAD"]),
            )
            .group_by(OutboundChannelMessage.status),
        )
        pending = db.scalar(
            select(func.count(OutboundChannelMessage.id)).where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.status == "PENDING",
            )
        ) or 0

        result["queue"] = {
            "events_received": event_period.get("RECEIVED", 0),
            "events_retry": event_attention.get("RETRY", 0),
            "events_dead": event_attention.get("DEAD", 0),
            "events_processed": event_period.get("PROCESSED", 0),
            "outbound_pending": int(pending),
            "outbound_retry": outbound_attention.get("RETRY", 0),
            "outbound_dead": outbound_attention.get("DEAD", 0),
            "outbound_sent": outbound_period.get("SENT", 0),
        }

        # The base dashboard preserves historical queue failures. Remove those
        # alert codes and recreate them from the active 15-minute window.
        result["alerts"] = [
            alert
            for alert in result["alerts"]
            if alert.get("code") not in {"DEAD_QUEUE_ITEMS", "QUEUE_RETRIES"}
        ]
        queue = result["queue"]
        if queue["events_dead"] or queue["outbound_dead"]:
            result["alerts"].insert(0, {
                "severity": "CRITICAL",
                "code": "DEAD_QUEUE_ITEMS",
                "message": "Existem mensagens recentes que atingiram o limite de tentativas.",
            })
        if queue["events_retry"] or queue["outbound_retry"]:
            result["alerts"].insert(0, {
                "severity": "WARNING",
                "code": "QUEUE_RETRIES",
                "message": "Existem mensagens recentes aguardando nova tentativa.",
            })

        return result

    @staticmethod
    def _counts(db: Session, statement) -> dict[str, int]:
        return {
            str(status): int(count)
            for status, count in db.execute(statement).all()
        }
