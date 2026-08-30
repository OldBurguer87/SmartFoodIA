from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalog import Store


def is_store_human_only(
    db: Session,
    *,
    store_id: UUID,
) -> bool:
    if settings.human_only_mode:
        return True

    operation_mode = db.scalar(
        select(Store.operation_mode).where(Store.id == store_id)
    )
    return operation_mode == "HUMAN_ONLY"
