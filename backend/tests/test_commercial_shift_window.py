from datetime import datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.commercial import StoreBusinessHours
from app.services.commercial_status import CommercialStatusService


TZ = ZoneInfo("America/Manaus")


def setup_store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Teste")
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
    db.commit()
    db.refresh(store)

    return db, store


def test_current_shift_explicit_closed_day_is_reliable_closed():
    db, store = setup_store()

    # 03/09/2026 = quinta-feira = weekday 3
    db.add(
        StoreBusinessHours(
            store_id=store.id,
            weekday=3,
            closed=True,
        )
    )
    db.commit()

    result = CommercialStatusService().current_shift_window(
        db,
        store.id,
        now=datetime(
            2026, 9, 3, 20, 0, tzinfo=TZ
        ),
    )

    assert result["active"] is False
    assert result["reliable"] is True
    assert result["started_at"] is None
    assert result["ends_at"] is None


def test_current_shift_supports_previous_day_overnight_window():
    db, store = setup_store()

    # Quarta-feira: abre 18:00 e fecha quinta 02:00.
    db.add(
        StoreBusinessHours(
            store_id=store.id,
            weekday=2,
            closed=False,
            open_time=time(18, 0),
            close_time=time(2, 0),
        )
    )
    db.commit()

    result = CommercialStatusService().current_shift_window(
        db,
        store.id,
        now=datetime(
            2026, 9, 3, 1, 0, tzinfo=TZ
        ),
    )

    assert result["active"] is True
    assert result["reliable"] is True

    assert result["started_at"] == datetime(
        2026, 9, 2, 18, 0, tzinfo=TZ
    )
    assert result["ends_at"] == datetime(
        2026, 9, 3, 2, 0, tzinfo=TZ
    )


def test_current_shift_incomplete_schedule_fails_open():
    db, store = setup_store()

    # Cadastro incompleto não pode bloquear a Olívia.
    db.add(
        StoreBusinessHours(
            store_id=store.id,
            weekday=3,
            closed=False,
            open_time=time(18, 0),
            close_time=None,
        )
    )
    db.commit()

    result = CommercialStatusService().current_shift_window(
        db,
        store.id,
        now=datetime(
            2026, 9, 3, 20, 0, tzinfo=TZ
        ),
    )

    assert result["active"] is False
    assert result["reliable"] is False
