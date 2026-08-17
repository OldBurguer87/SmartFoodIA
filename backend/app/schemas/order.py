from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CheckoutRequest(BaseModel):
    address_id: UUID | None = None
    payment_method: str = Field(
        pattern="^(PIX|CREDIT|DEBIT|CASH)$",
    )
    payment_type: str = Field(
        default="PENDING",
        pattern="^(PENDING|PREPAID)$",
    )
    change_for: Decimal | None = Field(default=None, ge=0)
    delivery_fee: Decimal = Field(default=Decimal("0.00"), ge=0)
    discount: Decimal = Field(default=Decimal("0.00"), ge=0)

    scheduled_for: datetime | None = None

    @model_validator(mode="after")
    def validate_cash(self):
        if self.payment_method != "CASH" and self.change_for is not None:
            raise ValueError("Troco só pode ser informado para pagamento em dinheiro.")
        return self


class OrderModifierRead(BaseModel):
    id: UUID
    external_code: str
    name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class OrderItemRead(BaseModel):
    id: UUID
    external_code: str
    name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    observations: str | None
    modifiers: list[OrderModifierRead]


class OrderAddressRead(BaseModel):
    street: str
    number: str
    neighborhood: str
    city: str
    state: str
    postal_code: str | None = None
    complement: str | None = None
    reference: str | None = None


class OrderRead(BaseModel):
    id: UUID
    display_id: str
    status: str
    service_mode: str
    scheduled_for: datetime | None = None
    payment_method: str
    payment_type: str
    change_for: Decimal | None
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    customer_name: str
    customer_phone: str
    address: OrderAddressRead | None
    items: list[OrderItemRead]
