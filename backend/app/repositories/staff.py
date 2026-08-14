from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

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

    def list_notifiable(
        self,
        db: Session,
        *,
        store_id: UUID,
    ) -> list[StoreStaffMember]:
        return list(
            db.scalars(
                select(StoreStaffMember)
                .where(
                    StoreStaffMember.store_id == store_id,
                    StoreStaffMember.active.is_(True),
                    StoreStaffMember.notify_whatsapp.is_(True),
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
