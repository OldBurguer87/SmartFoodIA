from datetime import time
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.olivia_prompt import OLIVIA_INSTRUCTIONS
from app.api.commercial_rules import RulesUpdate
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.commercial import (
    StoreBusinessHours,
    StoreCommercialRules,
)
from app.services.commercial_context import CommercialContextService


ONLINE_URL = "https://menu.exemplo.com/loja"


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


def test_commercial_context_exposes_only_configured_online_order_url() -> None:
    db, store = setup_store(
        online_order_url=ONLINE_URL,
    )

    context = CommercialContextService().build(
        db,
        store.id,
    )

    assert "CARDÁPIO/PEDIDO ONLINE OFICIAL" in context
    assert ONLINE_URL in context
    assert "NUNCA ofereça ou mencione este link espontaneamente" in context


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


def test_olivia_never_offers_online_menu_spontaneously() -> None:
    assert (
        "NUNCA ofereça, mencione ou envie espontaneamente link"
        in OLIVIA_INSTRUCTIONS
    )
    assert "no início de uma nova conversa mencione UMA ÚNICA VEZ" not in (
        OLIVIA_INSTRUCTIONS
    )


def test_olivia_uses_pdf_first_for_broad_menu_requests() -> None:
    assert "PDF PRIMEIRO" in OLIVIA_INSTRUCTIONS
    assert "quais hambúrgueres vocês têm?" in OLIVIA_INSTRUCTIONS
    assert "NÃO use browse_catalog, search_catalog ou search_knowledge" in (
        OLIVIA_INSTRUCTIONS
    )
    assert "Não pergunte ao cliente se prefere PDF" in OLIVIA_INSTRUCTIONS


def test_olivia_only_sends_online_link_when_explicitly_requested() -> None:
    assert (
        'Se o cliente pedir explicitamente "link", "site", "cardápio online"'
        in OLIVIA_INSTRUCTIONS
    )
    assert (
        "O PDF é o caminho preferencial para apresentação ampla"
        in OLIVIA_INSTRUCTIONS
    )

def test_olivia_does_not_invent_url_when_none_is_configured() -> None:
    assert "não há link online configurado" in OLIVIA_INSTRUCTIONS
    assert "Nunca invente, complete, encurte ou altere uma URL" in (
        OLIVIA_INSTRUCTIONS
    )


def test_online_order_url_blank_becomes_none() -> None:
    rules = RulesUpdate(online_order_url="   ")
    assert rules.online_order_url is None


def test_online_order_url_accepts_http_and_https() -> None:
    assert (
        RulesUpdate(
            online_order_url=" https://menu.exemplo.com/loja "
        ).online_order_url
        == "https://menu.exemplo.com/loja"
    )
    assert (
        RulesUpdate(
            online_order_url="http://menu.exemplo.com"
        ).online_order_url
        == "http://menu.exemplo.com"
    )


@pytest.mark.parametrize(
    "url",
    [
        "menu.exemplo.com",
        "ftp://menu.exemplo.com",
        "javascript:alert(1)",
        "https://",
    ],
)
def test_online_order_url_rejects_invalid_values(url: str) -> None:
    with pytest.raises(ValidationError):
        RulesUpdate(online_order_url=url)


def test_online_order_url_is_isolated_by_store() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Empresa Teste")
    db.add(company)
    db.flush()

    store_a = Store(
        company_id=company.id,
        name="Loja A",
        slug=f"loja-a-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    store_b = Store(
        company_id=company.id,
        name="Loja B",
        slug=f"loja-b-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )

    db.add_all([store_a, store_b])
    db.flush()

    db.add(
        StoreCommercialRules(
            store_id=store_a.id,
            average_prep_minutes=20,
            online_order_url="https://menu.exemplo.com/loja-a",
        )
    )
    db.add(
        StoreCommercialRules(
            store_id=store_b.id,
            average_prep_minutes=20,
            online_order_url=None,
        )
    )

    for store in (store_a, store_b):
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

    context_a = CommercialContextService().build(db, store_a.id)
    context_b = CommercialContextService().build(db, store_b.id)

    assert "https://menu.exemplo.com/loja-a" in context_a
    assert "https://menu.exemplo.com/loja-a" not in context_b
    assert "CARDÁPIO/PEDIDO ONLINE OFICIAL" not in context_b
