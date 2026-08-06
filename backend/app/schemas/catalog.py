from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    store_id: UUID
    category_id: UUID | None = None
    external_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    description: str | None = None
    price: Decimal = Field(ge=0)
    active: bool = True
    available_for_delivery: bool = True
    available_for_takeout: bool = True


class ProductRead(ProductCreate):
    id: UUID

    model_config = ConfigDict(from_attributes=True)
