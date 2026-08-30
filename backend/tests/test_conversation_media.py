from uuid import uuid4

import pytest

from app.services.conversation_media import (
    ConversationMediaStorage,
    ConversationMediaStorageError,
)


def test_conversation_media_storage_persists_file(
    tmp_path,
):
    storage = ConversationMediaStorage(
        root_path=tmp_path,
        max_bytes=1024,
    )

    store_id = uuid4()
    conversation_id = uuid4()
    content = b"imagem-de-teste"

    stored = storage.store(
        store_id=store_id,
        conversation_id=conversation_id,
        content=content,
        mime_type="image/jpeg",
        original_filename="../../foto.jpg",
    )

    path = storage.resolve(
        stored.relative_path
    )

    assert path.read_bytes() == content
    assert stored.mime_type == "image/jpeg"
    assert stored.file_size == len(content)
    assert stored.original_filename == "foto.jpg"
    assert stored.relative_path.endswith(".jpg")


def test_conversation_media_storage_rejects_oversize(
    tmp_path,
):
    storage = ConversationMediaStorage(
        root_path=tmp_path,
        max_bytes=4,
    )

    with pytest.raises(
        ConversationMediaStorageError
    ):
        storage.store(
            store_id=uuid4(),
            conversation_id=uuid4(),
            content=b"12345",
            mime_type="image/png",
        )


def test_conversation_media_storage_rejects_unknown_mime(
    tmp_path,
):
    storage = ConversationMediaStorage(
        root_path=tmp_path,
    )

    with pytest.raises(
        ConversationMediaStorageError
    ):
        storage.store(
            store_id=uuid4(),
            conversation_id=uuid4(),
            content=b"abc",
            mime_type="text/html",
        )


def test_conversation_media_storage_blocks_path_traversal(
    tmp_path,
):
    storage = ConversationMediaStorage(
        root_path=tmp_path,
    )

    with pytest.raises(
        ConversationMediaStorageError
    ):
        storage.resolve("../../etc/passwd")
