from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.operations import get_conversation
from app.database.base import Base
from app.models.catalog import Company, Store
from app.schemas.conversation import ConversationCreate, MessageCreate
from app.services.conversation import ConversationService


def test_conversation_detail_returns_messages():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(name='Old Burguer 87')
        db.add(company)
        db.flush()
        store = Store(
            company_id=company.id,
            name='Old Burguer 87',
            slug=f'old-{uuid4()}',
            city='Coari',
            state='AM',
            timezone='America/Manaus',
        )
        db.add(store)
        db.commit()
        db.refresh(store)

        conversation = ConversationService().get_or_create(
            db,
            ConversationCreate(
                store_id=store.id,
                channel='WHATSAPP',
                external_conversation_id='5597999999999',
            ),
        )
        ConversationService().add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction='INBOUND',
                sender_type='CUSTOMER',
                content='Olá',
            ),
        )

        body = get_conversation(conversation.id, db)
        assert body['messages'][0]['content'] == 'Olá'
        assert body['messages'][0]['sender_type'] == 'CUSTOMER'


def test_conversation_list_marks_only_current_shift_open_conversations(
    monkeypatch,
):
    from datetime import datetime, timedelta, timezone

    import app.api.operations as operations_api

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
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

        service = ConversationService()

        old_conversation = service.get_or_create(
            db,
            ConversationCreate(
                store_id=store.id,
                channel="WHATSAPP",
                external_conversation_id="5597000000001",
            ),
        )

        current_conversation = service.get_or_create(
            db,
            ConversationCreate(
                store_id=store.id,
                channel="WHATSAPP",
                external_conversation_id="5597000000002",
            ),
        )

        now = datetime.now(timezone.utc)
        shift_start = now - timedelta(hours=2)

        old_conversation.last_message_at = (
            shift_start - timedelta(minutes=1)
        )
        current_conversation.last_message_at = (
            shift_start + timedelta(minutes=1)
        )

        db.commit()

        monkeypatch.setattr(
            operations_api.commercial_status_service,
            "current_shift_window",
            lambda db, store_id: {
                "active": True,
                "reliable": True,
                "started_at": shift_start,
                "ends_at": now + timedelta(hours=4),
                "local_time": now,
            },
        )

        body = operations_api.list_conversations(
            store_id=store.id,
            status=None,
            limit=100,
            _access=None,
            db=db,
        )

        indexed = {
            item["external_conversation_id"]: item
            for item in body
        }

        assert (
            indexed["5597000000001"]["status"]
            == "OPEN"
        )
        assert (
            indexed["5597000000001"][
                "current_shift"
            ]
            is False
        )

        assert (
            indexed["5597000000002"][
                "current_shift"
            ]
            is True
        )
