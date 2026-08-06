from typing import Any

from pydantic import BaseModel, Field


class ToolExecutionRequest(BaseModel):
    tool_name: str = Field(min_length=2, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    requires_human: bool = False


from uuid import UUID

class OliviaReplyRequest(BaseModel):
    store_id: UUID
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=4000)
    customer_phone: str | None = Field(default=None, max_length=20)

class OliviaReplyResponse(BaseModel):
    conversation_id: UUID
    reply: str
