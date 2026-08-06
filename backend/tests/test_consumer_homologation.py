from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.integrations.consumer.auth import hash_token
from app.models.catalog import Company, Store
from app.models.integration import StoreIntegration
from app.services.consumer_partner import ConsumerPartnerService


def setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Empresa")
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

    integration = StoreIntegration(
        store_id=store.id,
        provider="CONSUMER",
        token_hash=hash_token("segredo"),
        merchant_external_id="merchant-1",
        merchant_name="Loja Teste",
        active=True,
    )
    db.add(integration)
    db.commit()
    db.refresh(store)
    db.refresh(integration)
    return db, store, integration


def test_diagnostics_returns_https_endpoints_and_checks():
    db, store, integration = setup_db()

    result = ConsumerPartnerService().diagnostics(
        db,
        store=store,
        integration=integration,
        base_url="https://api.exemplo.com/",
    )

    assert result.statusCode == 0
    assert result.integrationActive is True
    assert result.checks["merchant_configured"] is True
    assert result.checks["token_configured"] is True
    assert result.checks["https_base_url"] is True
    assert result.endpoints.polling.endswith(
        f"/consumer/{store.slug}/events"
    )
    assert "{order_id}" in result.endpoints.orderDetails


def test_diagnostics_flags_non_https_base_url():
    db, store, integration = setup_db()

    result = ConsumerPartnerService().diagnostics(
        db,
        store=store,
        integration=integration,
        base_url="http://localhost:8000",
    )

    assert result.checks["https_base_url"] is False
