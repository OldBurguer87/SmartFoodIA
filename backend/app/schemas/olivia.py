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
