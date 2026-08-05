from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModifierGroupCreate(BaseModel):
    store_id: UUID
    name: str = Field(min_length=2, max_length=140)
    description: str | None = None
    min_select: int = Field(default=0, ge=0)
    max_select: int = Field(default=1, ge=1)
    allow_repeat: bool = False
    display_order: int = Field(default=0, ge=0)
    active: bool = True

    @model_validator(mode="after")
    def validate_limits(self):
        if self.min_select > self.max_select:
            raise ValueError("min_select cannot be greater than max_select")
        return self


class ModifierGroupRead(ModifierGroupCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class ModifierCreate(BaseModel):
    store_id: UUID
    external_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    price: Decimal = Field(ge=0)
    active: bool = True


class ModifierRead(ModifierCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class ProductModifierGroupCreate(BaseModel):
    product_id: UUID
    modifier_group_id: UUID
    display_order: int = Field(default=0, ge=0)
    min_select_override: int | None = Field(default=None, ge=0)
    max_select_override: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_overrides(self):
        if (
            self.min_select_override is not None
            and self.max_select_override is not None
            and self.min_select_override > self.max_select_override
        ):
            raise ValueError("min_select_override cannot exceed max_select_override")
        return self


class ModifierGroupItemCreate(BaseModel):
    modifier_group_id: UUID
    modifier_id: UUID
    display_order: int = Field(default=0, ge=0)
    min_quantity: int = Field(default=0, ge=0)
    max_quantity: int = Field(default=1, ge=1)
    default_quantity: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_quantities(self):
        if self.min_quantity > self.max_quantity:
            raise ValueError("min_quantity cannot exceed max_quantity")
        if not self.min_quantity <= self.default_quantity <= self.max_quantity:
            raise ValueError("default_quantity must be within min/max bounds")
        return self
