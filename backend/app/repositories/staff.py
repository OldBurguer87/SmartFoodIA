from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.commercial import StoreBusinessHours
from app.models.staff import StoreStaffMember


class StaffRepository:
    def get_by_phone(
        self,
        db: Session,
        *,
        store_id: UUID,
        phone: str,
    ) -> StoreStaffMember | None:
        return db.scalar(
            select(StoreStaffMember).where(
                StoreStaffMember.store_id == store_id,
                StoreStaffMember.phone == phone,
                StoreStaffMember.active.is_(True),
            )
        )

    def is_operational_time(
        self,
        db: Session,
        *,
        store_id: UUID,
        now: datetime | None = None,
    ) -> bool:
        store = db.get(Store, store_id)
        if store is None:
            return False

        local_tz = ZoneInfo(store.timezone)
        current = now or datetime.now(timezone.utc)

        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        local_now = current.astimezone(local_tz)
        local_time = local_now.time().replace(tzinfo=None)
        weekday = local_now.weekday()

        today = db.scalar(
            select(StoreBusinessHours).where(
                StoreBusinessHours.store_id == store_id,
                StoreBusinessHours.weekday == weekday,
            )
        )

        if (
            today is not None
            and not today.closed
            and today.open_time is not None
            and today.close_time is not None
        ):
            if today.open_time <= today.close_time:
                if today.open_time <= local_time <= today.close_time:
                    return True
            elif local_time >= today.open_time:
                return True

        previous = db.scalar(
            select(StoreBusinessHours).where(
                StoreBusinessHours.store_id == store_id,
                StoreBusinessHours.weekday == ((weekday - 1) % 7),
            )
        )

        if (
            previous is not None
            and not previous.closed
            and previous.open_time is not None
            and previous.close_time is not None
            and previous.open_time > previous.close_time
            and local_time <= previous.close_time
        ):
            return True

        return False

    def list_notifiable(
        self,
        db: Session,
        *,
        store_id: UUID,
    ) -> list[StoreStaffMember]:
        if not self.is_operational_time(
            db,
            store_id=store_id,
        ):
            return []

        return list(
            db.scalars(
                select(StoreStaffMember)
                .where(
                    StoreStaffMember.store_id == store_id,
                    StoreStaffMember.active.is_(True),
                    StoreStaffMember.notify_whatsapp.is_(True),
                    StoreStaffMember.role != "MANAGER",
                )
                .order_by(StoreStaffMember.created_at)
            ).all()
        )

    def list_managers(
        self,
        db: Session,
        *,
        store_id: UUID,
    ) -> list[StoreStaffMember]:
        """
        Gerentes possuem uma fila de notificação separada.

        Não depende do horário operacional da loja porque esse nível
        é reservado para escalonamentos e problemas críticos.
        """
        return list(
            db.scalars(
                select(StoreStaffMember)
                .where(
                    StoreStaffMember.store_id == store_id,
                    StoreStaffMember.active.is_(True),
                    StoreStaffMember.notify_whatsapp.is_(True),
                    StoreStaffMember.role == "MANAGER",
                )
                .order_by(StoreStaffMember.created_at)
            ).all()
        )

    def get_by_current_conversation(
        self,
        db: Session,
        *,
        conversation_id: UUID,
    ) -> StoreStaffMember | None:
        return db.scalar(
            select(StoreStaffMember).where(
                StoreStaffMember.current_conversation_id == conversation_id,
                StoreStaffMember.active.is_(True),
            )
        )
