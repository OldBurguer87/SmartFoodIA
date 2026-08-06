from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.channel import ChannelRepository
from app.repositories.conversation import ConversationRepository
from app.schemas.conversation import (
    ConversationTakeoverRequest,
    HumanReplyRequest,
)
from app.services.conversation import (
    ConversationNotFoundError,
    ConversationService,
    ConversationStateError,
)

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])
conversations = ConversationService()
conversation_repository = ConversationRepository()
channel_repository = ChannelRepository()


def conversation_to_dict(conversation) -> dict:
    last_message = conversation.messages[-1] if conversation.messages else None
    return {
        "id": str(conversation.id),
        "store_id": str(conversation.store_id),
        "customer_id": str(conversation.customer_id)
        if conversation.customer_id
        else None,
        "channel": conversation.channel,
        "external_conversation_id": conversation.external_conversation_id,
        "status": conversation.status,
        "last_message_at": conversation.last_message_at,
        "last_message": (
            {
                "sender_type": last_message.sender_type,
                "content": last_message.content,
                "created_at": last_message.created_at,
            }
            if last_message
            else None
        ),
    }


@router.get("/stores/{store_id}/conversations")
def list_conversations(
    store_id: UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        conversation_to_dict(item)
        for item in conversation_repository.list_for_store(
            db,
            store_id=store_id,
            status=status,
            limit=limit,
        )
    ]



@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    messages = conversation_repository.list_messages(db, conversation_id, limit=200)
    payload = conversation_to_dict(conversation)
    payload["messages"] = [
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
    return payload

@router.post("/conversations/{conversation_id}/takeover")
def take_over(
    conversation_id: UUID,
    payload: ConversationTakeoverRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        conversation = conversations.take_over(
            db,
            conversation_id=conversation_id,
            assigned_to=payload.assigned_to,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.") from error
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return conversation_to_dict(conversation)


@router.post("/conversations/{conversation_id}/release")
def release_to_olivia(
    conversation_id: UUID,
    payload: ConversationTakeoverRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        conversation = conversations.release_to_olivia(
            db,
            conversation_id=conversation_id,
            assigned_to=payload.assigned_to,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.") from error
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return conversation_to_dict(conversation)


@router.post("/conversations/{conversation_id}/reply")
def human_reply(
    conversation_id: UUID,
    payload: HumanReplyRequest,
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if conversation.channel != "WHATSAPP":
        raise HTTPException(
            status_code=422,
            detail="Envio humano disponível somente para WhatsApp nesta versão.",
        )
    account = channel_repository.get_account_by_store(
        db,
        store_id=conversation.store_id,
        provider="WHATSAPP_CLOUD",
    )
    if account is None:
        raise HTTPException(
            status_code=422,
            detail="Conta WhatsApp ativa não encontrada para a loja.",
        )
    if not conversation.external_conversation_id:
        raise HTTPException(
            status_code=422,
            detail="Conversa sem destinatário externo.",
        )

    try:
        message = conversations.add_human_message(
            db,
            conversation_id=conversation_id,
            content=payload.content,
            assigned_to=payload.assigned_to,
        )
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    outbound = channel_repository.create_outbound(
        db,
        account=account,
        conversation_id=conversation.id,
        recipient=conversation.external_conversation_id,
        content=payload.content,
    )
    return {
        "message_id": str(message.id),
        "outbound_id": str(outbound.id),
        "status": outbound.status,
    }
