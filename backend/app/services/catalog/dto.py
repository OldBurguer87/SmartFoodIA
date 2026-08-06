from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ModifierDTO(BaseModel):
    id: UUID
    external_code: str
    name: str
    description: str | None
    price: Decimal
    min_quantity: int
    max_quantity: int
    default_quantity: int
    display_order: int

    model_config = ConfigDict(frozen=True)


class ModifierGroupDTO(BaseModel):
    id: UUID
    name: str
    description: str | None
    min_select: int
    max_select: int
    allow_repeat: bool
    display_order: int
    modifiers: tuple[ModifierDTO, ...]

    model_config = ConfigDict(frozen=True)


class ProductDTO(BaseModel):
    id: UUID
    store_id: UUID
    external_code: str
    name: str
    description: str | None
    price: Decimal
    category: str | None
    available_for_delivery: bool
    available_for_takeout: bool
    modifier_groups: tuple[ModifierGroupDTO, ...] = ()

    model_config = ConfigDict(frozen=True)


class ProductSearchResultDTO(BaseModel):
    product: ProductDTO
    score: float

    model_config = ConfigDict(frozen=True)
