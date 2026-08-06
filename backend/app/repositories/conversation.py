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
            Conversation.status == "OPEN",
        )
        if external_conversation_id is None:
            statement = statement.where(Conversation.external_conversation_id.is_(None))
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
