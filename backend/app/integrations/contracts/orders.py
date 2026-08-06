from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID
from sqlalchemy.orm import Session

@dataclass(frozen=True)
class IntegrationEvent:
    id: UUID
    order_id: UUID
    created_at: datetime
    code: str
    full_code: str

class OrderIntegrationAdapter(Protocol):
    provider: str
    def poll(self, db: Session, *, store_id: UUID, limit: int = 100) -> list[IntegrationEvent]: ...
    def serialize_order(self, db: Session, *, store_id: UUID, order_id: UUID, integration: Any) -> dict[str, Any]: ...
    def acknowledge_details_request(self, db: Session, *, store_id: UUID, order_id: UUID, code: str, full_code: str, reason: str | None = None) -> IntegrationEvent: ...
    def apply_external_status(self, db: Session, *, store_id: UUID, order_id: UUID, status: str, justification: str | None = None) -> tuple[str, bool]: ...
