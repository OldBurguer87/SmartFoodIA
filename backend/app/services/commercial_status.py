from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.commercial import StoreBusinessHours, StoreCommercialRules, StoreDeliveryZone


def normalize_zone_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    plain = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain.casefold()).strip()


class CommercialStatusService:
    def get_or_create_rules(self, db: Session, store_id: UUID) -> StoreCommercialRules:
        rules = db.scalar(select(StoreCommercialRules).where(StoreCommercialRules.store_id == store_id))
        if rules:
            return rules
        store = db.get(Store, store_id)
        if store is None:
            raise LookupError("Loja não encontrada.")
        rules = StoreCommercialRules(store_id=store_id)
        if store.slug == "old-burguer-87":
            rules.minimum_delivery_subtotal = Decimal("15.00")
            rules.delivery_fee_mode = "FIXED"
            rules.fixed_delivery_fee = Decimal("3.00")
            rules.average_prep_minutes = 20
        db.add(rules)
        db.commit()
        db.refresh(rules)
        return rules

    def current_status(self, db: Session, store_id: UUID, service_mode: str | None = None) -> dict:
        store = db.get(Store, store_id)
        if store is None:
            raise LookupError("Loja não encontrada.")
        rules = self.get_or_create_rules(db, store_id)
        now = datetime.now(ZoneInfo(store.timezone))
        day = db.scalar(select(StoreBusinessHours).where(StoreBusinessHours.store_id == store_id, StoreBusinessHours.weekday == now.weekday()))
        if rules.manual_paused:
            return {"open": False, "reason": rules.pause_reason or "Pedidos pausados temporariamente.", "local_time": now}
        if service_mode == "DELIVERY" and not rules.delivery_enabled:
            return {"open": False, "reason": "Delivery desativado.", "local_time": now}
        if service_mode == "TAKEOUT" and not rules.takeout_enabled:
            return {"open": False, "reason": "Retirada desativada.", "local_time": now}
        if day is None:
            return {
                "open": False,
                "reason": "Horário de funcionamento ainda não cadastrado; não confirme que a loja está aberta.",
                "local_time": now,
                "schedule_configured": False,
            }
        if day.closed:
            return {"open": False, "reason": "Restaurante fechado hoje.", "local_time": now, "schedule_configured": True}
        local_time = now.time().replace(tzinfo=None)
        if day.open_time and day.close_time:
            inside = day.open_time <= local_time <= day.close_time if day.open_time <= day.close_time else (local_time >= day.open_time or local_time <= day.close_time)
            if not inside:
                return {"open": False, "reason": "Fora do horário de funcionamento.", "local_time": now, "schedule_configured": True}
        cutoff = day.delivery_until if service_mode == "DELIVERY" else day.takeout_until if service_mode == "TAKEOUT" else None
        if cutoff and local_time > cutoff:
            return {"open": False, "reason": "Horário limite desta modalidade encerrado.", "local_time": now, "schedule_configured": True}
        return {"open": True, "reason": "Aceitando pedidos.", "local_time": now, "schedule_configured": True}

    def validate_scheduled_time(
        self,
        db: Session,
        store_id: UUID,
        *,
        scheduled_for: datetime,
        service_mode: str,
    ) -> dict:
        store = db.get(Store, store_id)
        if store is None:
            raise ValueError("Loja não encontrada.")

        rules = self.get_or_create_rules(db, store_id)
        local_tz = ZoneInfo(store.timezone)
        now = datetime.now(local_tz)

        if scheduled_for.tzinfo is None:
            scheduled_local = scheduled_for.replace(tzinfo=local_tz)
        else:
            scheduled_local = scheduled_for.astimezone(local_tz)

        prep_minutes = int(rules.average_prep_minutes or 0)

        if prep_minutes <= 0:
            raise ValueError(
                "Tempo médio de preparo não configurado para pedidos agendados."
            )

        if rules.manual_paused:
            raise ValueError(
                rules.pause_reason or "Pedidos pausados temporariamente."
            )

        if service_mode == "DELIVERY" and not rules.delivery_enabled:
            raise ValueError("Delivery desativado.")

        if service_mode == "TAKEOUT" and not rules.takeout_enabled:
            raise ValueError("Retirada desativada.")

        if scheduled_local <= now:
            raise ValueError(
                "O horário do pedido agendado precisa estar no futuro."
            )

        day = db.scalar(
            select(StoreBusinessHours).where(
                StoreBusinessHours.store_id == store_id,
                StoreBusinessHours.weekday == scheduled_local.weekday(),
            )
        )

        if day is None:
            raise ValueError(
                "Horário de funcionamento ainda não cadastrado para este dia."
            )

        if day.closed:
            raise ValueError("A loja estará fechada no dia escolhido.")

        if day.open_time is None or day.close_time is None:
            raise ValueError(
                "Horário de funcionamento incompleto para o dia escolhido."
            )

        requested_time = scheduled_local.time().replace(tzinfo=None)

        if day.open_time <= day.close_time:
            inside = day.open_time <= requested_time <= day.close_time
        else:
            inside = (
                requested_time >= day.open_time
                or requested_time <= day.close_time
            )

        if not inside:
            raise ValueError(
                "O horário escolhido está fora do horário de funcionamento."
            )

        cutoff = (
            day.delivery_until
            if service_mode == "DELIVERY"
            else day.takeout_until
            if service_mode == "TAKEOUT"
            else None
        )

        if cutoff and requested_time > cutoff:
            raise ValueError(
                "O horário escolhido ultrapassa o limite desta modalidade."
            )

        opening_at = datetime.combine(
            scheduled_local.date(),
            day.open_time,
            tzinfo=local_tz,
        )

        if (
            day.open_time > day.close_time
            and requested_time <= day.close_time
        ):
            opening_at -= timedelta(days=1)

        earliest_ready = max(
            now + timedelta(minutes=prep_minutes),
            opening_at + timedelta(minutes=prep_minutes),
        )

        if scheduled_local < earliest_ready:
            raise ValueError(
                "Não há tempo suficiente para preparar o pedido. "
                f"O primeiro horário possível é "
                f"{earliest_ready.strftime('%d/%m às %H:%M')}."
            )

        release_at = scheduled_local - timedelta(
            minutes=prep_minutes
        )

        return {
            "scheduled_for": scheduled_local,
            "release_at": release_at,
            "prep_minutes": prep_minutes,
        }

    def delivery_fee(self, db: Session, store_id: UUID, neighborhood: str | None) -> Decimal:
        rules = self.get_or_create_rules(db, store_id)
        if rules.delivery_fee_mode == "FIXED":
            return Decimal(rules.fixed_delivery_fee)
        if not neighborhood:
            raise ValueError("Informe o bairro para calcular a taxa de entrega.")
        zone = db.scalar(select(StoreDeliveryZone).where(StoreDeliveryZone.store_id == store_id, StoreDeliveryZone.normalized_name == normalize_zone_name(neighborhood), StoreDeliveryZone.active.is_(True)))
        if zone is None:
            raise ValueError("Bairro/região sem taxa cadastrada.")
        if not zone.delivery_allowed:
            raise ValueError("Este bairro/região não é atendido para delivery.")
        return Decimal(zone.fee)
