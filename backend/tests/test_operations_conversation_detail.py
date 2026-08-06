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
