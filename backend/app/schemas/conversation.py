from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    store_id: UUID
    customer_id: UUID | None = None
    channel: str = Field(default="WHATSAPP", min_length=2, max_length=30)
    external_conversation_id: str | None = Field(default=None, max_length=120)


class MessageCreate(BaseModel):
    direction: str = Field(pattern="^(INBOUND|OUTBOUND)$")
    sender_type: str = Field(pattern="^(CUSTOMER|OLIVIA|HUMAN|SYSTEM)$")
    content_type: str = Field(default="TEXT", max_length=20)
    content: str = Field(min_length=1)
    external_message_id: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] | None = None


class HumanTicketCreate(BaseModel):
    conversation_id: UUID | None = None
    customer_id: UUID | None = None
    category: str = Field(min_length=2, max_length=30)
    priority: str = Field(default="NORMAL", pattern="^(LOW|NORMAL|HIGH|URGENT)$")
    reason: str = Field(min_length=3, max_length=500)
    customer_message: str = Field(min_length=1)


class KnowledgeGapCreate(BaseModel):
    conversation_id: UUID | None = None
    ticket_id: UUID | None = None
    question: str = Field(min_length=3, max_length=1000)


class KnowledgeGapResolve(BaseModel):
    answer: str = Field(min_length=2, max_length=2000)


class AIEventCreate(BaseModel):
    conversation_id: UUID | None = None
    event_type: str = Field(min_length=2, max_length=60)
    tool_name: str | None = Field(default=None, max_length=100)
    success: bool = True
    duration_ms: int | None = Field(default=None, ge=0)
    payload_json: dict[str, Any] | None = None
    error_message: str | None = None
