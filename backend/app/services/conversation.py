from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.conversation import (
    AIEvent,
    Conversation,
    HumanTicket,
    KnowledgeGap,
    Message,
)
from app.repositories.conversation import ConversationRepository
from app.models.staff import StoreStaffMember
from app.schemas.conversation import (
    AIEventCreate,
    ConversationCreate,
    HumanTicketCreate,
    KnowledgeGapCreate,
    KnowledgeGapResolve,
    MessageCreate,
)


class ConversationNotFoundError(LookupError):
    pass


class ConversationStateError(ValueError):
    pass


def normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


class ConversationService:
    def __init__(self, repository: ConversationRepository | None = None) -> None:
        self.repository = repository or ConversationRepository()

    def get_or_create(
        self,
        db: Session,
        payload: ConversationCreate,
    ) -> Conversation:
        existing = self.repository.get_open(
            db,
            store_id=payload.store_id,
            channel=payload.channel,
            external_conversation_id=payload.external_conversation_id,
        )
        if existing is not None:
            if payload.customer_id is not None and existing.customer_id is None:
                existing.customer_id = payload.customer_id
                db.commit()
                db.refresh(existing)
            return existing

        conversation = Conversation(
            store_id=payload.store_id,
            customer_id=payload.customer_id,
            channel=payload.channel,
            external_conversation_id=payload.external_conversation_id,
            status="OPEN",
            last_message_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    def add_message(
        self,
        db: Session,
        *,
        conversation_id: UUID,
        payload: MessageCreate,
    ) -> Message:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))

        message = Message(
            conversation_id=conversation_id,
            direction=payload.direction,
            sender_type=payload.sender_type,
            content_type=payload.content_type,
            content=payload.content,
            external_message_id=payload.external_message_id,
            metadata_json=payload.metadata_json,
        )
        conversation.last_message_at = datetime.now(timezone.utc)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    def wait_for_human(
        self,
        db: Session,
        *,
        conversation_id: UUID,
        reason: str,
        ticket_id: UUID | None = None,
    ) -> Conversation:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.status == "CLOSED":
            raise ConversationStateError(
                "Conversa encerrada não pode aguardar atendimento humano."
            )

        conversation.status = "WAITING_HUMAN"
        db.add(
            AIEvent(
                store_id=conversation.store_id,
                conversation_id=conversation.id,
                event_type="HUMAN_WAITING",
                success=True,
                payload_json={
                    "assigned_to": "fila-humana",
                    "reason": reason,
                    "ticket_id": str(ticket_id) if ticket_id else None,
                },
            )
        )
        db.commit()
        db.refresh(conversation)
        return conversation

    def take_over(
        self,
        db: Session,
        *,
        conversation_id: UUID,
        assigned_to: str,
    ) -> Conversation:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.status == "CLOSED":
            raise ConversationStateError(
                "Conversa encerrada não pode ser assumida."
            )
        if conversation.status == "RESUMING_OLIVIA":
            raise ConversationStateError(
                "A Olívia está retomando esta conversa neste momento."
            )
        conversation.status = "HUMAN"
        db.add(
            AIEvent(
                store_id=conversation.store_id,
                conversation_id=conversation.id,
                event_type="HUMAN_TAKEOVER",
                success=True,
                payload_json={"assigned_to": assigned_to},
            )
        )
        db.commit()
        db.refresh(conversation)
        return conversation

    def release_to_olivia(
        self,
        db: Session,
        *,
        conversation_id: UUID,
        assigned_to: str,
    ) -> Conversation:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.status != "HUMAN":
            raise ConversationStateError(
                "Conversa não está sob atendimento humano."
            )
        conversation.status = "OPEN"

        db.execute(
            update(StoreStaffMember)
            .where(
                StoreStaffMember.current_conversation_id == conversation.id
            )
            .values(current_conversation_id=None)
        )

        db.add(
            AIEvent(
                store_id=conversation.store_id,
                conversation_id=conversation.id,
                event_type="HUMAN_RELEASE",
                success=True,
                payload_json={"assigned_to": assigned_to},
            )
        )
        db.commit()
        db.refresh(conversation)
        return conversation

    def add_human_message(
        self,
        db: Session,
        *,
        conversation_id: UUID,
        content: str,
        assigned_to: str,
    ) -> Message:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.status != "HUMAN":
            raise ConversationStateError(
                "Assuma a conversa antes de enviar uma resposta humana."
            )
        return self.add_message(
            db,
            conversation_id=conversation_id,
            payload=MessageCreate(
                direction="OUTBOUND",
                sender_type="HUMAN",
                content=content,
                metadata_json={"assigned_to": assigned_to},
            ),
        )

    def assign_ticket(
        self,
        db: Session,
        *,
        ticket_id: UUID,
        assigned_to: str,
    ) -> HumanTicket:
        ticket = self.repository.get_ticket(db, ticket_id)
        if ticket is None:
            raise ConversationNotFoundError(str(ticket_id))
        if ticket.status == "RESOLVED":
            raise ConversationStateError(
                "Ticket resolvido não pode ser reatribuído."
            )
        ticket.assigned_to = assigned_to
        ticket.status = "IN_PROGRESS"
        db.commit()
        db.refresh(ticket)
        return ticket

    def resolve_ticket(
        self,
        db: Session,
        *,
        ticket_id: UUID,
        resolution: str,
        assigned_to: str,
    ) -> HumanTicket:
        ticket = self.repository.get_ticket(db, ticket_id)
        if ticket is None:
            raise ConversationNotFoundError(str(ticket_id))
        ticket.assigned_to = assigned_to
        ticket.resolution = resolution
        ticket.status = "RESOLVED"
        db.commit()
        db.refresh(ticket)
        return ticket

    def find_knowledge_answer(
        self,
        db: Session,
        *,
        store_id: UUID,
        question: str,
    ) -> KnowledgeGap | None:
        return self.repository.get_resolved_gap(
            db,
            store_id=store_id,
            normalized_question=normalize_question(question),
        )

    def create_ticket(
        self,
        db: Session,
        *,
        store_id: UUID,
        payload: HumanTicketCreate,
    ) -> HumanTicket:
        ticket = HumanTicket(
            store_id=store_id,
            conversation_id=payload.conversation_id,
            customer_id=payload.customer_id,
            category=payload.category,
            priority=payload.priority,
            status="OPEN",
            reason=payload.reason,
            customer_message=payload.customer_message,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket

    def create_or_increment_gap(
        self,
        db: Session,
        *,
        store_id: UUID,
        payload: KnowledgeGapCreate,
    ) -> KnowledgeGap:
        normalized = normalize_question(payload.question)
        existing = self.repository.get_open_gap(
            db,
            store_id=store_id,
            normalized_question=normalized,
        )
        if existing is not None:
            existing.occurrences += 1
            if (
                existing.conversation_id is None
                and payload.conversation_id is not None
            ):
                existing.conversation_id = payload.conversation_id
            if existing.ticket_id is None and payload.ticket_id is not None:
                existing.ticket_id = payload.ticket_id
            db.commit()
            db.refresh(existing)
            return existing

        gap = KnowledgeGap(
            store_id=store_id,
            conversation_id=payload.conversation_id,
            ticket_id=payload.ticket_id,
            question=payload.question,
            normalized_question=normalized,
            status="OPEN",
            occurrences=1,
        )
        db.add(gap)
        db.commit()
        db.refresh(gap)
        return gap

    def resolve_gap(
        self,
        db: Session,
        *,
        gap_id: UUID,
        payload: KnowledgeGapResolve,
    ) -> KnowledgeGap:
        gap = db.get(KnowledgeGap, gap_id)
        if gap is None:
            raise ConversationNotFoundError(str(gap_id))
        gap.answer = payload.answer
        gap.status = "RESOLVED"
        db.commit()
        db.refresh(gap)
        return gap

    def record_event(
        self,
        db: Session,
        *,
        store_id: UUID,
        payload: AIEventCreate,
    ) -> AIEvent:
        event = AIEvent(
            store_id=store_id,
            conversation_id=payload.conversation_id,
            event_type=payload.event_type,
            tool_name=payload.tool_name,
            success=payload.success,
            duration_ms=payload.duration_ms,
            payload_json=payload.payload_json,
            error_message=payload.error_message,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
