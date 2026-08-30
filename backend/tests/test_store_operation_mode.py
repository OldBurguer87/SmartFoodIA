from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.operations import (
    get_store_operation_mode,
    update_store_operation_mode,
)
from app.core.config import settings
from app.database.base import Base
from app.models.catalog import Company, Store
from app.schemas.conversation import StoreOperationModeRequest
from app.services.auth import StoreAccess


def setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Old Burguer 87")
    db.add(company)
    db.flush()

    store = Store(
        company_id=company.id,
        name="Old Burguer 87",
        slug=f"old-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.commit()
    db.refresh(store)

    access = StoreAccess(
        store_id=store.id,
        company_id=company.id,
        role="ADMIN",
        is_platform_admin=False,
    )
    return db, store, access


def test_store_defaults_to_olivia(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", False)
    db, store, access = setup_db()

    result = get_store_operation_mode(
        store_id=store.id,
        access=access,
        db=db,
    )

    assert store.operation_mode == "OLIVIA"
    assert result["configured_mode"] == "OLIVIA"
    assert result["effective_mode"] == "OLIVIA"
    assert result["server_forced_human"] is False
    assert result["can_change"] is True


def test_server_override_forces_human_mode(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", True)
    db, store, access = setup_db()

    result = get_store_operation_mode(
        store_id=store.id,
        access=access,
        db=db,
    )

    assert result["configured_mode"] == "OLIVIA"
    assert result["effective_mode"] == "HUMAN_ONLY"
    assert result["server_forced_human"] is True


def test_store_can_be_changed_to_human_only(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", False)
    db, store, access = setup_db()

    result = update_store_operation_mode(
        store_id=store.id,
        payload=StoreOperationModeRequest(
            operation_mode="HUMAN_ONLY",
        ),
        _access=access,
        db=db,
    )

    db.refresh(store)
    assert store.operation_mode == "HUMAN_ONLY"
    assert result["configured_mode"] == "HUMAN_ONLY"
    assert result["effective_mode"] == "HUMAN_ONLY"


def test_server_override_blocks_reactivating_olivia(monkeypatch):
    monkeypatch.setattr(settings, "human_only_mode", True)
    db, store, access = setup_db()
    store.operation_mode = "HUMAN_ONLY"
    db.commit()

    with pytest.raises(HTTPException) as error:
        update_store_operation_mode(
            store_id=store.id,
            payload=StoreOperationModeRequest(
                operation_mode="OLIVIA",
            ),
            _access=access,
            db=db,
        )

    assert error.value.status_code == 409
    db.refresh(store)
    assert store.operation_mode == "HUMAN_ONLY"
