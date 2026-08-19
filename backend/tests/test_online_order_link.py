from datetime import time
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.olivia_prompt import OLIVIA_INSTRUCTIONS
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.commercial import (
    StoreBusinessHours,
    StoreCommercialRules,
)
from app.services.commercial_context import CommercialContextService


ONLINE_URL = "https://oldburguer87.menudino.com.br"


def setup_store(
    *,
    online_order_url: str | None,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Empresa Teste")
    db.add(company)
    db.flush()

    store = Store(
        company_id=company.id,
        name="Loja Teste",
        slug=f"loja-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.flush()

    rules = StoreCommercialRules(
        store_id=store.id,
        average_prep_minutes=20,
        online_order_url=online_order_url,
    )
    db.add(rules)

    for weekday in range(7):
        db.add(
            StoreBusinessHours(
                store_id=store.id,
                weekday=weekday,
                closed=False,
                open_time=time(0, 0),
                close_time=time(23, 59),
                delivery_until=time(23, 59),
                takeout_until=time(23, 59),
            )
        )

    db.commit()
    return db, store


def test_commercial_context_exposes_online_order_url() -> None:
    db, store = setup_store(
        online_order_url=ONLINE_URL,
    )

    context = CommercialContextService().build(
        db,
        store.id,
    )

    assert "CARDÁPIO/PEDIDO ONLINE OFICIAL" in context
    assert ONLINE_URL in context


def test_commercial_context_omits_online_order_when_not_configured() -> None:
    db, store = setup_store(
        online_order_url=None,
    )

    context = CommercialContextService().build(
        db,
        store.id,
    )

    assert "CARDÁPIO/PEDIDO ONLINE OFICIAL" not in context
    assert ONLINE_URL not in context


def test_olivia_prompt_has_online_order_behavior() -> None:
    assert "UMA ÚNICA VEZ" in OLIVIA_INSTRUCTIONS
    assert "três opções" in OLIVIA_INSTRUCTIONS
    assert '"cardápio online"' in OLIVIA_INSTRUCTIONS
    assert "URL exata" in OLIVIA_INSTRUCTIONS
