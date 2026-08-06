from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.tools.context import ToolContext
from app.ai.tools.knowledge import SearchKnowledgeTool
from app.database.base import Base
from app.models.catalog import Company, Store
from app.schemas.conversation import (
    HumanTicketCreate,
    KnowledgeGapCreate,
    KnowledgeGapResolve,
)
from app.services.conversation import ConversationService


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
    return db, store


def test_ticket_can_be_assigned_and_resolved():
    db, store = setup_db()
    service = ConversationService()
    ticket = service.create_ticket(
        db,
        store_id=store.id,
        payload=HumanTicketCreate(
            category="CATALOG",
            priority="HIGH",
            reason="Informação não confirmada",
            customer_message="O molho é artesanal?",
        ),
    )

    assigned = service.assign_ticket(
        db,
        ticket_id=ticket.id,
        assigned_to="Maria",
    )
    assert assigned.status == "IN_PROGRESS"
    assert assigned.assigned_to == "Maria"

    resolved = service.resolve_ticket(
        db,
        ticket_id=ticket.id,
        resolution="Confirmado: o molho é artesanal.",
        assigned_to="Maria",
    )
    assert resolved.status == "RESOLVED"
    assert "artesanal" in resolved.resolution


def test_resolved_knowledge_can_be_found_with_equivalent_question():
    db, store = setup_db()
    service = ConversationService()
    gap = service.create_or_increment_gap(
        db,
        store_id=store.id,
        payload=KnowledgeGapCreate(
            question="O molho barbecue é artesanal?"
        ),
    )
    service.resolve_gap(
        db,
        gap_id=gap.id,
        payload=KnowledgeGapResolve(
            answer="Sim, o molho barbecue é artesanal."
        ),
    )

    found = service.find_knowledge_answer(
        db,
        store_id=store.id,
        question="o molho barbecue e artesanal?",
    )
    assert found is not None
    assert found.answer == "Sim, o molho barbecue é artesanal."


def test_knowledge_tool_returns_only_approved_answer():
    db, store = setup_db()
    service = ConversationService()
    gap = service.create_or_increment_gap(
        db,
        store_id=store.id,
        payload=KnowledgeGapCreate(question="Tem opção sem lactose?"),
    )

    tool = SearchKnowledgeTool(ToolContext(db=db, store_id=store.id))
    missing = tool.execute(question="Tem opção sem lactose?")
    assert missing.ok is False

    service.resolve_gap(
        db,
        gap_id=gap.id,
        payload=KnowledgeGapResolve(
            answer="No momento não temos opção sem lactose."
        ),
    )
    found = tool.execute(question="tem opcao sem lactose?")
    assert found.ok is True
    assert "não temos" in found.data["answer"]
