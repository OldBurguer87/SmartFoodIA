from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import settings


class ConversationMediaStorageError(ValueError):
    pass


_ALLOWED_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ): ".docx",
    "application/vnd.ms-excel": ".xls",
    (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ): ".xlsx",
    "text/plain": ".txt",
}


@dataclass(frozen=True)
class StoredConversationMedia:
    relative_path: str
    mime_type: str
    file_size: int
    sha256: str
    original_filename: str | None


class ConversationMediaStorage:
    def __init__(
        self,
        *,
        root_path: str | Path | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.root_path = Path(
            root_path
            or settings.conversation_media_storage_path
        )

        self.max_bytes = (
            max_bytes
            if max_bytes is not None
            else settings.conversation_media_max_bytes
        )

    @staticmethod
    def _normalize_mime(
        mime_type: str | None,
    ) -> str:
        return (
            str(mime_type or "")
            .split(";")[0]
            .strip()
            .lower()
        )

    @staticmethod
    def _safe_original_filename(
        value: str | None,
    ) -> str | None:
        if not value:
            return None

        filename = Path(str(value)).name.strip()

        return filename or None

    def store(
        self,
        *,
        store_id: UUID,
        conversation_id: UUID,
        content: bytes,
        mime_type: str | None,
        original_filename: str | None = None,
    ) -> StoredConversationMedia:
        if not content:
            raise ConversationMediaStorageError(
                "Arquivo de midia vazio."
            )

        if len(content) > self.max_bytes:
            raise ConversationMediaStorageError(
                "Arquivo de midia excede o limite permitido."
            )

        normalized_mime = self._normalize_mime(
            mime_type
        )

        extension = _ALLOWED_MIME_EXTENSIONS.get(
            normalized_mime
        )

        if extension is None:
            raise ConversationMediaStorageError(
                "Formato de midia nao permitido: "
                f"{normalized_mime or 'desconhecido'}."
            )

        relative_path = (
            Path(str(store_id))
            / str(conversation_id)
            / f"{uuid4()}{extension}"
        )

        destination = self.root_path / relative_path

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(content)

        return StoredConversationMedia(
            relative_path=relative_path.as_posix(),
            mime_type=normalized_mime,
            file_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            original_filename=(
                self._safe_original_filename(
                    original_filename
                )
            ),
        )

    def resolve(
        self,
        relative_path: str,
    ) -> Path:
        if not relative_path:
            raise ConversationMediaStorageError(
                "Caminho de midia ausente."
            )

        root = self.root_path.resolve()
        candidate = (
            self.root_path / relative_path
        ).resolve()

        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ConversationMediaStorageError(
                "Caminho de midia invalido."
            ) from error

        return candidate
