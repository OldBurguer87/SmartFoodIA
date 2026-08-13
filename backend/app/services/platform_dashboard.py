from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.conversation import Conversation, HumanTicket
from app.models.integration import StoreIntegration
from app.models.order import Order


class PlatformDashboardService:
    ATTENTION_MINUTES = 15
    CONSUMER_WARNING_SECONDS = 120
    CONSUMER_CRITICAL_SECONDS = 300
    AUTO_PREFIX = "[AUTO-MONITOR]"

    def overview(self, db: Session, *, hours: int = 24) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)
        attention_since = now - timedelta(minutes=self.ATTENTION_MINUTES)
        stores = list(db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.name)).all())

        clients = [self._client(db, store, since=since, now=now) for store in stores]
        account_ids = select(ChannelAccount.id)

        queue_attention = db.scalar(
            select(func.count(OutboundChannelMessage.id)).where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.updated_at >= attention_since,
                OutboundChannelMessage.status.in_(["RETRY", "DEAD"]),
            )
        ) or 0
        sent = db.scalar(
            select(func.count(OutboundChannelMessage.id)).where(
                OutboundChannelMessage.channel_account_id.in_(account_ids),
                OutboundChannelMessage.created_at >= since,
                OutboundChannelMessage.status == "SENT",
            )
        ) or 0

        platform_issues = self._platform_issues(db)
        smartfoodia = {
            "status": "ATTENTION" if platform_issues or queue_attention else "OPERATIONAL",
            "api": "OPERATIONAL",
            "openai": "ATTENTION" if "OPENAI" in platform_issues else "OPERATIONAL",
            "whatsapp": "ATTENTION" if "WHATSAPP" in platform_issues else "OPERATIONAL",
            "queue": "ATTENTION" if queue_attention or "QUEUE" in platform_issues else "OPERATIONAL",
            "messages_sent": int(sent),
            "active_alerts": sorted(platform_issues),
        }

        return {
            "generated_at": now,
            "period_hours": hours,
            "smartfoodia": smartfoodia,
            "summary": {
                "clients_total": len(clients),
                "clients_attention": sum(1 for client in clients if client["status"] != "OPERATIONAL"),
                "orders_total": sum(client["orders"] for client in clients),
                "revenue_total": float(sum((Decimal(str(client["revenue"])) for client in clients), Decimal("0"))),
                "active_conversations": sum(client["active_conversations"] for client in clients),
            },
            "clients": clients,
        }

    def _client(self, db: Session, store: Store, *, since: datetime, now: datetime) -> dict:
        order_row = db.execute(
            select(func.count(Order.id), func.coalesce(func.sum(Order.total), 0)).where(
                Order.store_id == store.id,
                Order.created_at >= since,
            )
        ).one()
        active_conversations = db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.store_id == store.id,
                Conversation.status.in_(["OPEN", "HUMAN"]),
            )
        ) or 0
        urgent_tickets = db.scalar(
            select(func.count(HumanTicket.id)).where(
                HumanTicket.store_id == store.id,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
                HumanTicket.priority == "URGENT",
            )
        ) or 0
        integrations = list(db.scalars(
            select(StoreIntegration).where(StoreIntegration.store_id == store.id).order_by(StoreIntegration.provider)
        ).all())
        integration_items = [self._integration(item, now=now) for item in integrations]
        auto_issues = set(db.scalars(
            select(HumanTicket.reason).where(
                HumanTicket.store_id == store.id,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
                HumanTicket.reason.like(f"{self.AUTO_PREFIX}%"),
            )
        ).all())
        client_issue = any(item["status"] != "OPERATIONAL" for item in integration_items)
        client_issue = client_issue or any(reason.endswith(" CONSUMER") for reason in auto_issues)

        return {
            "store_id": str(store.id),
            "name": store.name,
            "slug": store.slug,
            "city": store.city,
            "state": store.state,
            "status": "ATTENTION" if client_issue else "OPERATIONAL",
            "orders": int(order_row[0] or 0),
            "revenue": float(Decimal(order_row[1] or 0)),
            "active_conversations": int(active_conversations),
            "urgent_tickets": int(urgent_tickets),
            "integrations": integration_items,
        }

    def _integration(self, integration: StoreIntegration, *, now: datetime) -> dict:
        status = "OPERATIONAL" if integration.active else "ATTENTION"
        age_seconds = max(0, int((now - integration.updated_at).total_seconds()))
        detail = "Ativa"
        if integration.provider == "CONSUMER" and integration.active:
            if age_seconds > self.CONSUMER_CRITICAL_SECONDS:
                status = "ATTENTION"
                detail = f"Sem polling há {age_seconds // 60} minuto(s)"
            elif age_seconds > self.CONSUMER_WARNING_SECONDS:
                status = "WARNING"
                detail = f"Polling atrasado há {age_seconds // 60} minuto(s)"
            else:
                detail = "Polling ativo"
        elif not integration.active:
            detail = "Integração inativa"

        return {
            "provider": integration.provider,
            "merchant_name": integration.merchant_name,
            "status": status,
            "detail": detail,
            "last_activity_at": integration.updated_at,
        }

    def _platform_issues(self, db: Session) -> set[str]:
        reasons = set(db.scalars(
            select(HumanTicket.reason).where(
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
                HumanTicket.reason.like(f"{self.AUTO_PREFIX}%"),
            )
        ).all())
        issues = set()
        for code in ("OPENAI", "WHATSAPP", "QUEUE"):
            if any(reason.endswith(f" {code}") for reason in reasons):
                issues.add(code)
        return issues
