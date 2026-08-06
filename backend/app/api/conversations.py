from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.conversation import ConversationRepository
from app.schemas.conversation import (
    AIEventCreate,
    ConversationCreate,
    HumanTicketCreate,
    KnowledgeGapCreate,
    KnowledgeGapResolve,
    MessageCreate,
)
from app.services.conversation import (
    ConversationNotFoundError,
    ConversationService,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
service = ConversationService()
repository = ConversationRepository()


@router.post("")
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
) -> dict:
    conversation = service.get_or_create(db, payload)
    return {
        "id": str(conversation.id),
        "store_id": str(conversation.store_id),
        "customer_id": str(conversation.customer_id)
        if conversation.customer_id
        else None,
        "channel": conversation.channel,
        "external_conversation_id": conversation.external_conversation_id,
        "status": conversation.status,
    }


@router.post("/{conversation_id}/messages")
def add_message(
    conversation_id: UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> dict:
    try:
        message = service.add_message(
            db,
            conversation_id=conversation_id,
            payload=payload,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.") from error

    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "direction": message.direction,
        "sender_type": message.sender_type,
        "content_type": message.content_type,
        "content": message.content,
        "created_at": message.created_at,
    }


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    conversation = repository.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    messages = repository.list_messages(db, conversation_id, limit=limit)
    return [
        {
            "id": str(message.id),
            "direction": message.direction,
            "sender_type": message.sender_type,
            "content_type": message.content_type,
            "content": message.content,
            "metadata_json": message.metadata_json,
            "created_at": message.created_at,
        }
        for message in messages
    ]


@router.post("/stores/{store_id}/tickets")
def create_ticket(
    store_id: UUID,
    payload: HumanTicketCreate,
    db: Session = Depends(get_db),
) -> dict:
    ticket = service.create_ticket(db, store_id=store_id, payload=payload)
    return {
        "id": str(ticket.id),
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
    }


@router.post("/stores/{store_id}/knowledge-gaps")
def create_knowledge_gap(
    store_id: UUID,
    payload: KnowledgeGapCreate,
    db: Session = Depends(get_db),
) -> dict:
    gap = service.create_or_increment_gap(db, store_id=store_id, payload=payload)
    return {
        "id": str(gap.id),
        "status": gap.status,
        "question": gap.question,
        "occurrences": gap.occurrences,
    }


@router.patch("/knowledge-gaps/{gap_id}/resolve")
def resolve_knowledge_gap(
    gap_id: UUID,
    payload: KnowledgeGapResolve,
    db: Session = Depends(get_db),
) -> dict:
    try:
        gap = service.resolve_gap(db, gap_id=gap_id, payload=payload)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Lacuna de conhecimento não encontrada.",
        ) from error
    return {
        "id": str(gap.id),
        "status": gap.status,
        "answer": gap.answer,
    }


@router.post("/stores/{store_id}/events")
def record_ai_event(
    store_id: UUID,
    payload: AIEventCreate,
    db: Session = Depends(get_db),
) -> dict:
    event = service.record_event(db, store_id=store_id, payload=payload)
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "success": event.success,
    }
