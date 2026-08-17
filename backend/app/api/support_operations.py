from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.api.deps import require_store_access
from app.database.session import get_db
from app.models.conversation import HumanTicket, KnowledgeGap
from app.repositories.conversation import ConversationRepository
from app.schemas.conversation import (
    HumanTicketAssign,
    HumanTicketResolve,
    KnowledgeGapResolve,
    KnowledgeSearchRequest,
)
from app.services.auth import (
    AuthenticatedUser,
    StoreAccess,
    resolve_store_access,
)
from app.services.conversation import (
    ConversationNotFoundError,
    ConversationService,
    ConversationStateError,
)

router = APIRouter(prefix="/api/v1/operations", tags=["support-operations"])
service = ConversationService()
repository = ConversationRepository()


def require_ticket_access(
    ticket_id: UUID,
    authenticated: AuthenticatedUser = Depends(current_auth),
    db: Session = Depends(get_db),
) -> StoreAccess:
    ticket = repository.get_ticket(db, ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket não encontrado.",
        )

    access = resolve_store_access(
        db,
        authenticated.user,
        ticket.store_id,
    )

    if access is None:
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a esta loja.",
        )

    return access


def require_ticket_write_access(
    access: StoreAccess = Depends(require_ticket_access),
) -> StoreAccess:
    if not access.can_write:
        raise HTTPException(
            status_code=403,
            detail="Seu usuário não pode alterar esta loja.",
        )

    return access


def require_gap_access(
    gap_id: UUID,
    authenticated: AuthenticatedUser = Depends(current_auth),
    db: Session = Depends(get_db),
) -> StoreAccess:
    gap = db.get(KnowledgeGap, gap_id)

    if gap is None:
        raise HTTPException(
            status_code=404,
            detail="Lacuna de conhecimento não encontrada.",
        )

    access = resolve_store_access(
        db,
        authenticated.user,
        gap.store_id,
    )

    if access is None:
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a esta loja.",
        )

    return access


def require_gap_write_access(
    access: StoreAccess = Depends(require_gap_access),
) -> StoreAccess:
    if not access.can_write:
        raise HTTPException(
            status_code=403,
            detail="Seu usuário não pode alterar esta loja.",
        )

    return access


def ticket_to_dict(ticket) -> dict:
    return {
        "id": str(ticket.id),
        "store_id": str(ticket.store_id),
        "conversation_id": str(ticket.conversation_id)
        if ticket.conversation_id
        else None,
        "customer_id": str(ticket.customer_id) if ticket.customer_id else None,
        "category": ticket.category,
        "priority": ticket.priority,
        "status": ticket.status,
        "reason": ticket.reason,
        "customer_message": ticket.customer_message,
        "resolution": ticket.resolution,
        "assigned_to": ticket.assigned_to,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def gap_to_dict(gap) -> dict:
    return {
        "id": str(gap.id),
        "store_id": str(gap.store_id),
        "conversation_id": str(gap.conversation_id)
        if gap.conversation_id
        else None,
        "ticket_id": str(gap.ticket_id) if gap.ticket_id else None,
        "question": gap.question,
        "answer": gap.answer,
        "status": gap.status,
        "occurrences": gap.occurrences,
        "created_at": gap.created_at,
        "updated_at": gap.updated_at,
    }


@router.get("/stores/{store_id}/tickets")
def list_tickets(
    store_id: UUID,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(require_store_access),
) -> list[dict]:
    return [
        ticket_to_dict(ticket)
        for ticket in repository.list_tickets(
            db,
            store_id=store_id,
            status=status,
            priority=priority,
            limit=limit,
        )
    ]


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(
    ticket_id: UUID,
    payload: HumanTicketAssign,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_ticket_write_access,
    ),
) -> dict:
    try:
        ticket = service.assign_ticket(
            db,
            ticket_id=ticket_id,
            assigned_to=payload.assigned_to,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket não encontrado.") from error
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ticket_to_dict(ticket)


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: UUID,
    payload: HumanTicketResolve,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_ticket_write_access,
    ),
) -> dict:
    try:
        ticket = service.resolve_ticket(
            db,
            ticket_id=ticket_id,
            resolution=payload.resolution,
            assigned_to=payload.assigned_to,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket não encontrado.") from error
    return ticket_to_dict(ticket)


@router.get("/stores/{store_id}/knowledge-gaps")
def list_knowledge_gaps(
    store_id: UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(require_store_access),
) -> list[dict]:
    return [
        gap_to_dict(gap)
        for gap in repository.list_knowledge_gaps(
            db,
            store_id=store_id,
            status=status,
            limit=limit,
        )
    ]


@router.post("/knowledge-gaps/{gap_id}/resolve")
def resolve_gap(
    gap_id: UUID,
    payload: KnowledgeGapResolve,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_gap_write_access,
    ),
) -> dict:
    try:
        gap = service.resolve_gap(db, gap_id=gap_id, payload=payload)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Lacuna de conhecimento não encontrada.",
        ) from error
    return gap_to_dict(gap)


@router.post("/stores/{store_id}/knowledge/search")
def search_knowledge(
    store_id: UUID,
    payload: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(require_store_access),
) -> dict:
    gap = service.find_knowledge_answer(
        db,
        store_id=store_id,
        question=payload.question,
    )
    if gap is None:
        raise HTTPException(
            status_code=404,
            detail="Resposta aprovada não encontrada.",
        )
    return gap_to_dict(gap)
