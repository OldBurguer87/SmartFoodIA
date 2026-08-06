from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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
    EventCode: Literal["ODR"]
    EventFullCode: str | None = Field(default=None, max_length=80)
    EventFull: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_details_request(self):
        if (
            self.EventFullCode is not None
            and self.EventFullCode.strip().upper() != "ORDER_DETAILS_REQUESTED"
        ):
            raise ValueError(
                "EventFullCode deve ser ORDER_DETAILS_REQUESTED para o evento ODR."
            )
        return self


class ConsumerStatusRequest(BaseModel):
    orderId: UUID
    status: str = Field(min_length=2, max_length=40)
    justification: str | None = Field(default=None, max_length=500)


class ConsumerStatusResponse(BaseModel):
    statusCode: int = 0
    reasonPhrase: str | None = None
