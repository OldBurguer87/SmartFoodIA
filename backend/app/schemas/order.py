from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CheckoutPaymentRequest(BaseModel):
    method: str = Field(
        pattern="^(PIX|CREDIT|DEBIT|CASH)$",
    )
    amount: Decimal = Field(gt=0)
    change_for: Decimal | None = Field(default=None, ge=0)
    payment_type: str = Field(
        default="PENDING",
        pattern="^(PENDING|PREPAID)$",
    )

    @model_validator(mode="after")
    def normalize_payment(self):
        if self.method != "CASH" and self.change_for is not None:
            raise ValueError(
                "Troco só pode ser informado na parcela em dinheiro."
            )

        self.payment_type = (
            "PREPAID"
            if self.method == "PIX"
            else "PENDING"
        )
        return self


class CheckoutRequest(BaseModel):
    address_id: UUID | None = None

    payment_method: str = Field(
        pattern="^(PIX|CREDIT|DEBIT|CASH|MIXED)$",
    )
    payment_type: str = Field(
        default="PENDING",
        pattern="^(PENDING|PREPAID)$",
    )
    change_for: Decimal | None = Field(default=None, ge=0)

    payments: list[CheckoutPaymentRequest] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    delivery_fee: Decimal = Field(default=Decimal("0.00"), ge=0)
    discount: Decimal = Field(default=Decimal("0.00"), ge=0)
    scheduled_for: datetime | None = None

    @model_validator(mode="after")
    def normalize_payment(self):
        if self.payments:
            methods = [
                payment.method
                for payment in self.payments
            ]

            if len(set(methods)) != 2:
                raise ValueError(
                    "As duas formas de pagamento devem ser diferentes."
                )

            if self.change_for is not None:
                raise ValueError(
                    "No pagamento misto, informe o troco "
                    "dentro da parcela CASH."
                )

            self.payment_method = "MIXED"
            self.payment_type = "PENDING"
            self.change_for = None
            return self

        if self.payment_method == "MIXED":
            raise ValueError(
                "Pagamento MIXED exige exatamente duas parcelas."
            )

        if self.payment_method != "CASH" and self.change_for is not None:
            raise ValueError(
                "Troco só pode ser informado para pagamento em dinheiro."
            )

        self.payment_type = (
            "PREPAID"
            if self.payment_method == "PIX"
            else "PENDING"
        )
        return self


class OrderPaymentRead(BaseModel):
    method: str
    payment_type: str
    amount: Decimal
    change_for: Decimal | None = None
    position: int


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
    payments: list[OrderPaymentRead] = Field(default_factory=list)
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    customer_name: str
    customer_phone: str
    address: OrderAddressRead | None
    items: list[OrderItemRead]
