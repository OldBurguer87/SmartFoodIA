from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation, HumanTicket, KnowledgeGap, Message


class ConversationRepository:
    def get(self, db: Session, conversation_id: UUID) -> Conversation | None:
        return db.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )

    def get_open(
        self,
        db: Session,
        *,
        store_id: UUID,
        channel: str,
        external_conversation_id: str | None,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.store_id == store_id,
            Conversation.channel == channel,
            Conversation.status.in_(["OPEN", "HUMAN"]),
        )
        if external_conversation_id is None:
            statement = statement.where(
                Conversation.external_conversation_id.is_(None)
            )
        else:
            statement = statement.where(
                Conversation.external_conversation_id == external_conversation_id
            )
        return db.scalar(statement.order_by(Conversation.created_at.desc()))

    def list_messages(
        self,
        db: Session,
        conversation_id: UUID,
        *,
        limit: int = 50,
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(db.scalars(statement).all())
        messages.reverse()
        return messages

    def list_for_store(
        self,
        db: Session,
        *,
        store_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(Conversation.store_id == store_id)
            .options(selectinload(Conversation.messages))
            .order_by(Conversation.last_message_at.desc())
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(Conversation.status == status)
        return list(db.scalars(statement).all())

    def list_tickets(
        self,
        db: Session,
        *,
        store_id: UUID,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[HumanTicket]:
        statement = (
            select(HumanTicket)
            .where(HumanTicket.store_id == store_id)
            .order_by(HumanTicket.created_at.desc())
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(HumanTicket.status == status)
        if priority is not None:
            statement = statement.where(HumanTicket.priority == priority)
        return list(db.scalars(statement).all())

    def list_knowledge_gaps(
        self,
        db: Session,
        *,
        store_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeGap]:
        statement = (
            select(KnowledgeGap)
            .where(KnowledgeGap.store_id == store_id)
            .order_by(
                KnowledgeGap.occurrences.desc(),
                KnowledgeGap.updated_at.desc(),
            )
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(KnowledgeGap.status == status)
        return list(db.scalars(statement).all())

    def get_resolved_gap(
        self,
        db: Session,
        *,
        store_id: UUID,
        normalized_question: str,
    ) -> KnowledgeGap | None:
        return db.scalar(
            select(KnowledgeGap).where(
                KnowledgeGap.store_id == store_id,
                KnowledgeGap.normalized_question == normalized_question,
                KnowledgeGap.status == "RESOLVED",
                KnowledgeGap.answer.is_not(None),
            )
        )

    def get_open_gap(
        self,
        db: Session,
        *,
        store_id: UUID,
        normalized_question: str,
    ) -> KnowledgeGap | None:
        return db.scalar(
            select(KnowledgeGap).where(
                KnowledgeGap.store_id == store_id,
                KnowledgeGap.normalized_question == normalized_question,
                KnowledgeGap.status == "OPEN",
            )
        )

    def get_ticket(self, db: Session, ticket_id: UUID) -> HumanTicket | None:
        return db.get(HumanTicket, ticket_id)
