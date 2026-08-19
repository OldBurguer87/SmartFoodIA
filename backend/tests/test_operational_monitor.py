from uuid import uuid4

import app.models  # noqa: F401

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.conversation import HumanTicket
from app.services.operational_monitor import OperationalMonitorService


class FakeManagerEscalation:
    def __init__(self):
        self.calls = []

    def notify_system(self, db, **kwargs):
        self.calls.append(kwargs)
        return 1


def _setup_db():
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

    return db, store


def test_operational_incident_notifies_manager_only_once():
    db, store = _setup_db()

    monitor = OperationalMonitorService()
    manager = FakeManagerEscalation()
    monitor.manager = manager

    # Força um único incidente crítico sem depender
    # das integrações reais.
    monitor._checks = lambda db, store_id: {
        "OPENAI": "OpenAI indisponível para teste.",
        "WHATSAPP": None,
        "CONSUMER": None,
        "QUEUE": None,
    }

    first = monitor.run(db)

    assert first["stores_checked"] == 1
    assert first["tickets_opened"] == 1
    assert len(manager.calls) == 1

    call = manager.calls[0]

    assert call["store_id"] == store.id
    assert call["title"] == "Falha crítica: OPENAI"
    assert call["source"] == "OPERATIONAL_MONITOR_OPENAI"
    assert "indisponível" in call["details"]

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.store_id == store.id,
                HumanTicket.reason == "[AUTO-MONITOR] OPENAI",
            )
        )
    )

    assert len(tickets) == 1
    assert tickets[0].status == "OPEN"
    assert tickets[0].priority == "URGENT"

    # A mesma falha continua ativa.
    # Deve atualizar/reutilizar o ticket existente,
    # sem gerar novo alerta ao gerente.
    second = monitor.run(db)

    assert second["stores_checked"] == 1
    assert second["tickets_opened"] == 0
    assert len(manager.calls) == 1

    tickets = list(
        db.scalars(
            select(HumanTicket).where(
                HumanTicket.store_id == store.id,
                HumanTicket.reason == "[AUTO-MONITOR] OPENAI",
            )
        )
    )

    assert len(tickets) == 1
    assert tickets[0].status == "OPEN"
