from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ToolContext:
    db: Session
    store_id: UUID
    conversation_id: UUID | None = None
    customer_phone: str | None = None
