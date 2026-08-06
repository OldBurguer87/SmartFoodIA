from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ModifierSelection(BaseModel):
    external_code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=20)


class CartCreate(BaseModel):
    store_id: UUID
    customer_id: UUID
    service_mode: str = Field(default="DELIVERY", pattern="^(DELIVERY|TAKEOUT)$")


class CartItemAdd(BaseModel):
    product_external_code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=99)
    observations: str | None = Field(default=None, max_length=500)
    modifiers: list[ModifierSelection] = Field(default_factory=list)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=99)
    observations: str | None = Field(default=None, max_length=500)


class CartModifierRead(BaseModel):
    id: UUID
    external_code: str
    name: str
    quantity: int
    unit_price: Decimal
    total: Decimal


class CartItemRead(BaseModel):
    id: UUID
    product_external_code: str
    product_name: str
    quantity: int
    unit_price: Decimal
    observations: str | None
    modifiers: list[CartModifierRead]
    total: Decimal


class CartRead(BaseModel):
    id: UUID
    store_id: UUID
    customer_id: UUID
    status: str
    service_mode: str
    items: list[CartItemRead]
    subtotal: Decimal
