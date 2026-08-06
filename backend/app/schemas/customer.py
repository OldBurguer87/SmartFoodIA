import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Telefone deve conter entre 10 e 15 dígitos.")
    return digits


class CustomerCreate(BaseModel):
    store_id: UUID
    name: str = Field(min_length=2, max_length=160)
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone(value)


class CustomerRead(CustomerCreate):
    id: UUID
    active: bool

    model_config = ConfigDict(from_attributes=True)


class AddressCreate(BaseModel):
    label: str = Field(default="Principal", min_length=2, max_length=80)
    street: str = Field(min_length=2, max_length=180)
    number: str = Field(min_length=1, max_length=30)
    neighborhood: str = Field(min_length=2, max_length=120)
    city: str = Field(default="Coari", min_length=2, max_length=100)
    state: str = Field(default="AM", min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=12)
    complement: str | None = Field(default=None, max_length=180)
    reference: str | None = Field(default=None, max_length=240)
    is_default: bool = False


class AddressRead(AddressCreate):
    id: UUID
    customer_id: UUID
    active: bool

    model_config = ConfigDict(from_attributes=True)
