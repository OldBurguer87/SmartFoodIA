from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.conversation import Conversation, Message
from app.services.conversation_media import ConversationMediaStorage
from app.services.conversation_media_retention import (
    ConversationMediaRetentionService,
)


NOW = datetime(2026, 9, 6, 3, 0, tzinfo=timezone.utc)


def setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Teste Media")
    db.add(company)
    db.flush()

    store = Store(
        company_id=company.id,
        name="Loja Media",
        slug=f"media-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.flush()

    conversation = Conversation(
        store_id=store.id,
        channel="WHATSAPP",
        external_conversation_id="5597999990000",
        status="OPEN",
    )
    db.add(conversation)
    db.commit()

    return db, store, conversation


def test_conversation_media_is_purged_after_48_hours(tmp_path):
    db, store, conversation = setup_db()

    storage = ConversationMediaStorage(root_path=tmp_path)

    old_stored = storage.store(
        store_id=store.id,
        conversation_id=conversation.id,
        content=b"imagem-antiga",
        mime_type="image/png",
        original_filename="antiga.png",
    )

    recent_stored = storage.store(
        store_id=store.id,
        conversation_id=conversation.id,
        content=b"imagem-recente",
        mime_type="image/png",
        original_filename="recente.png",
    )

    old_message = Message(
        conversation_id=conversation.id,
        direction="INBOUND",
        sender_type="CUSTOMER",
        content_type="IMAGE",
        content="[Imagem recebida]",
        metadata_json={
            "stored_media": True,
            "stored_media_path": old_stored.relative_path,
            "mime_type": old_stored.mime_type,
            "file_size": old_stored.file_size,
            "sha256": old_stored.sha256,
            "filename": "antiga.png",
        },
        created_at=NOW - timedelta(hours=49),
    )

    recent_message = Message(
        conversation_id=conversation.id,
        direction="INBOUND",
        sender_type="CUSTOMER",
        content_type="IMAGE",
        content="[Imagem recebida]",
        metadata_json={
            "stored_media": True,
            "stored_media_path": recent_stored.relative_path,
            "mime_type": recent_stored.mime_type,
            "file_size": recent_stored.file_size,
            "sha256": recent_stored.sha256,
            "filename": "recente.png",
        },
        created_at=NOW - timedelta(hours=47),
    )

    db.add_all([old_message, recent_message])
    db.commit()

    old_path = tmp_path / old_stored.relative_path
    recent_path = tmp_path / recent_stored.relative_path

    assert old_path.is_file()
    assert recent_path.is_file()

    result = ConversationMediaRetentionService(
        storage=storage,
        retention_hours=48,
    ).run_once(
        db,
        now=NOW,
    )

    assert result.examined == 1
    assert result.purged == 1
    assert result.files_deleted == 1
    assert result.db_errors == 0

    db.refresh(old_message)
    db.refresh(recent_message)

    old_metadata = old_message.metadata_json or {}
    recent_metadata = recent_message.metadata_json or {}

    assert old_metadata["stored_media"] is False
    assert old_metadata["media_expired"] is True
    assert "media_expired_at" in old_metadata
    assert "stored_media_path" not in old_metadata
    assert "sha256" not in old_metadata
    assert "file_size" not in old_metadata

    assert not old_path.exists()

    assert recent_metadata["stored_media"] is True
    assert recent_path.is_file()

    db.close()
