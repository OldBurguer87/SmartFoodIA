from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConsumerEventRead(BaseModel):
    id: UUID
    orderId: UUID
    createdAt: datetime
    fullCode: str
    code: str


class ConsumerPollingResponse(BaseModel):
    items: list[ConsumerEventRead] = Field(default_factory=list)
    statusCode: int = 0
    reasonPhrase: str | None = None


class ConsumerOrderEventRequest(BaseModel):
    OrderId: UUID
    EventCode: str = Field(min_length=2, max_length=20)
    EventFullCode: str | None = Field(default=None, max_length=80)
    EventFull: str | None = Field(default=None, max_length=500)


class ConsumerStatusRequest(BaseModel):
    orderId: UUID
    status: str = Field(min_length=2, max_length=40)
    justification: str | None = Field(default=None, max_length=500)


class ConsumerStatusResponse(BaseModel):
    statusCode: int = 0
    reasonPhrase: str | None = None
