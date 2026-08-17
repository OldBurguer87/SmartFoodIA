from datetime import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.commercial import (
    StoreBusinessHours,
    StoreCommercialRules,
)


def configure_store_open(
    db: Session,
    store: Store,
) -> None:
    rules = db.scalar(
        select(StoreCommercialRules).where(
            StoreCommercialRules.store_id == store.id
        )
    )

    if rules is None:
        rules = StoreCommercialRules(
            store_id=store.id,
        )
        db.add(rules)

    rules.delivery_fee_mode = "FIXED"
    rules.fixed_delivery_fee = Decimal("5.00")
    rules.average_prep_minutes = 20

    for weekday in range(7):
        db.add(
            StoreBusinessHours(
                store_id=store.id,
                weekday=weekday,
                closed=False,
                open_time=time(0, 0, 0),
                close_time=time(23, 59, 59),
                delivery_until=time(23, 59, 59),
                takeout_until=time(23, 59, 59),
            )
        )

    db.commit()
