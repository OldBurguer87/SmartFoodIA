from uuid import UUID

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage


class ChannelRepository:
    def get_account_by_external_id(
        self,
        db: Session,
        *,
        provider: str,
        external_account_id: str,
    ) -> ChannelAccount | None:
        return db.scalar(
            select(ChannelAccount).where(
                ChannelAccount.provider == provider,
                ChannelAccount.external_account_id == external_account_id,
                ChannelAccount.active.is_(True),
            )
        )


    def get_account_by_verify_token_hash(
        self,
        db: Session,
        *,
        provider: str,
        verify_token_hash: str,
    ) -> ChannelAccount | None:
        return db.scalar(
            select(ChannelAccount).where(
                ChannelAccount.provider == provider,
                ChannelAccount.verify_token_hash == verify_token_hash,
                ChannelAccount.active.is_(True),
            )
        )

    def get_account(self, db: Session, account_id: UUID) -> ChannelAccount | None:
        return db.get(ChannelAccount, account_id)

    def get_event(
        self,
        db: Session,
        *,
        provider: str,
        external_event_id: str,
    ) -> ChannelEvent | None:
        return db.scalar(
            select(ChannelEvent).where(
                ChannelEvent.provider == provider,
                ChannelEvent.external_event_id == external_event_id,
            )
        )

    def create_event(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        external_event_id: str,
        event_type: str,
        payload: dict,
    ) -> ChannelEvent:
        event = ChannelEvent(
            channel_account_id=account.id,
            provider=account.provider,
            external_event_id=external_event_id,
            event_type=event_type,
            status="RECEIVED",
            attempts=0,
            payload_json=payload,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    def create_outbound(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        conversation_id: UUID | None,
        recipient: str,
        content: str,
    ) -> OutboundChannelMessage:
        message = OutboundChannelMessage(
            channel_account_id=account.id,
            conversation_id=conversation_id,
            provider=account.provider,
            recipient=recipient,
            content_type="TEXT",
            content=content,
            status="PENDING",
            attempts=0,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message


    def list_due_events(self, db: Session, *, now: datetime, limit: int = 50) -> list[ChannelEvent]:
        statement = (select(ChannelEvent).where(ChannelEvent.status.in_(["RECEIVED", "RETRY"]), or_(ChannelEvent.next_attempt_at.is_(None), ChannelEvent.next_attempt_at <= now)).order_by(ChannelEvent.created_at).limit(limit))
        return list(db.scalars(statement).all())

    def list_due_outbound(self, db: Session, *, now: datetime, limit: int = 50) -> list[OutboundChannelMessage]:
        statement = (select(OutboundChannelMessage).where(OutboundChannelMessage.status.in_(["PENDING", "RETRY"]), or_(OutboundChannelMessage.next_attempt_at.is_(None), OutboundChannelMessage.next_attempt_at <= now)).order_by(OutboundChannelMessage.created_at).limit(limit))
        return list(db.scalars(statement).all())
