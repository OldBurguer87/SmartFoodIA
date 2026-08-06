from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session


class OrderStatusNotifier(Protocol):
    def notify_status_change(
        self,
        db: Session,
        *,
        store_id: UUID,
        order_id: UUID,
        status: str,
    ) -> bool:
        ...
