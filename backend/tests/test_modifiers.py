from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.modifiers import ModifierCreate, ModifierGroupCreate, ModifierGroupItemCreate


def test_modifier_group_accepts_valid_limits() -> None:
    group = ModifierGroupCreate(
        store_id=uuid4(), name="Adicionais", min_select=0, max_select=4
    )
    assert group.max_select == 4


def test_modifier_group_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        ModifierGroupCreate(
            store_id=uuid4(), name="Molhos", min_select=3, max_select=1
        )


def test_modifier_requires_nonnegative_price() -> None:
    with pytest.raises(ValidationError):
        ModifierCreate(
            store_id=uuid4(),
            external_code="37",
            name="Bacon",
            price=Decimal("-1.00"),
        )


def test_group_item_validates_default_quantity() -> None:
    with pytest.raises(ValidationError):
        ModifierGroupItemCreate(
            modifier_group_id=uuid4(),
            modifier_id=uuid4(),
            min_quantity=0,
            max_quantity=2,
            default_quantity=3,
        )
