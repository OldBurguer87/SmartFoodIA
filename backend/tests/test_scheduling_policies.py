from datetime import datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.commercial import (
    StoreBusinessHours,
    StoreCommercialRules,
)
from app.services.commercial_status import CommercialStatusService


MANAUS = ZoneInfo("America/Manaus")
NOW = datetime(2026, 8, 17, 15, 0, tzinfo=MANAUS)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return NOW.replace(tzinfo=None)
        return NOW.astimezone(tz)


def setup_context(
    monkeypatch,
    *,
    open_time: time = time(0, 0),
    close_time: time = time(23, 59),
):
    monkeypatch.setattr(
        "app.services.commercial_status.datetime",
        FrozenDateTime,
    )

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
        allow_scheduled_orders=True,
        allow_scheduled_when_closed=True,
    )
    db.add(rules)

    for weekday in range(7):
        db.add(
            StoreBusinessHours(
                store_id=store.id,
                weekday=weekday,
                closed=False,
                open_time=open_time,
                close_time=close_time,
                delivery_until=close_time,
                takeout_until=close_time,
            )
        )

    db.commit()

    return db, store, rules


def test_default_policy_preserves_current_scheduling_behavior(
    monkeypatch,
) -> None:
    db, store, _rules = setup_context(monkeypatch)

    result = CommercialStatusService().validate_scheduled_time(
        db,
        store.id,
        scheduled_for=datetime(
            2026,
            8,
            17,
            18,
            0,
            tzinfo=MANAUS,
        ),
        service_mode="DELIVERY",
    )

    assert result["scheduled_for"] == datetime(
        2026,
        8,
        17,
        18,
        0,
        tzinfo=MANAUS,
    )
    assert result["release_at"] == datetime(
        2026,
        8,
        17,
        17,
        40,
        tzinfo=MANAUS,
    )


def test_scheduled_orders_can_be_disabled(
    monkeypatch,
) -> None:
    db, store, rules = setup_context(monkeypatch)
    rules.allow_scheduled_orders = False
    db.commit()

    with pytest.raises(
        ValueError,
        match="agendados",
    ):
        CommercialStatusService().validate_scheduled_time(
            db,
            store.id,
            scheduled_for=datetime(
                2026,
                8,
                17,
                18,
                0,
                tzinfo=MANAUS,
            ),
            service_mode="DELIVERY",
        )


def test_scheduling_while_store_is_closed_can_be_disabled(
    monkeypatch,
) -> None:
    db, store, rules = setup_context(
        monkeypatch,
        open_time=time(17, 0),
        close_time=time(23, 59),
    )
    rules.allow_scheduled_when_closed = False
    db.commit()

    with pytest.raises(
        ValueError,
        match="fechada",
    ):
        CommercialStatusService().validate_scheduled_time(
            db,
            store.id,
            scheduled_for=datetime(
                2026,
                8,
                17,
                18,
                0,
                tzinfo=MANAUS,
            ),
            service_mode="DELIVERY",
        )


def test_custom_minimum_notice_is_enforced(
    monkeypatch,
) -> None:
    db, store, rules = setup_context(monkeypatch)
    rules.scheduled_min_notice_minutes = 120
    db.commit()

    with pytest.raises(
        ValueError,
        match="antecedência",
    ):
        CommercialStatusService().validate_scheduled_time(
            db,
            store.id,
            scheduled_for=datetime(
                2026,
                8,
                17,
                16,
                0,
                tzinfo=MANAUS,
            ),
            service_mode="DELIVERY",
        )


def test_maximum_days_ahead_is_enforced(
    monkeypatch,
) -> None:
    db, store, rules = setup_context(monkeypatch)
    rules.scheduled_max_days_ahead = 2
    db.commit()

    with pytest.raises(
        ValueError,
        match="dias",
    ):
        CommercialStatusService().validate_scheduled_time(
            db,
            store.id,
            scheduled_for=datetime(
                2026,
                8,
                20,
                18,
                0,
                tzinfo=MANAUS,
            ),
            service_mode="DELIVERY",
        )


def test_default_policy_allows_scheduling_while_store_is_closed(
    monkeypatch,
) -> None:
    db, store, _rules = setup_context(
        monkeypatch,
        open_time=time(17, 0),
        close_time=time(23, 59),
    )

    result = CommercialStatusService().validate_scheduled_time(
        db,
        store.id,
        scheduled_for=datetime(
            2026,
            8,
            17,
            17,
            20,
            tzinfo=MANAUS,
        ),
        service_mode="DELIVERY",
    )

    assert result["scheduled_for"] == datetime(
        2026,
        8,
        17,
        17,
        20,
        tzinfo=MANAUS,
    )
    assert result["release_at"] == datetime(
        2026,
        8,
        17,
        17,
        0,
        tzinfo=MANAUS,
    )


def test_exact_minimum_notice_is_allowed(
    monkeypatch,
) -> None:
    db, store, rules = setup_context(monkeypatch)
    rules.scheduled_min_notice_minutes = 120
    db.commit()

    result = CommercialStatusService().validate_scheduled_time(
        db,
        store.id,
        scheduled_for=datetime(
            2026,
            8,
            17,
            17,
            0,
            tzinfo=MANAUS,
        ),
        service_mode="DELIVERY",
    )

    assert result["scheduled_for"].hour == 17
    assert result["scheduled_for"].minute == 0


def test_exact_maximum_days_ahead_is_allowed(
    monkeypatch,
) -> None:
    db, store, rules = setup_context(monkeypatch)
    rules.scheduled_max_days_ahead = 2
    db.commit()

    result = CommercialStatusService().validate_scheduled_time(
        db,
        store.id,
        scheduled_for=datetime(
            2026,
            8,
            19,
            18,
            0,
            tzinfo=MANAUS,
        ),
        service_mode="DELIVERY",
    )

    assert result["scheduled_for"].date().isoformat() == "2026-08-19"
