from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Message
from app.services.conversation_media import (
    ConversationMediaStorage,
    ConversationMediaStorageError,
)


@dataclass(frozen=True)
class ConversationMediaRetentionResult:
    examined: int = 0
    purged: int = 0
    files_deleted: int = 0
    files_missing: int = 0
    skipped_invalid_path: int = 0
    file_delete_errors: int = 0
    file_restore_errors: int = 0
    db_errors: int = 0


class ConversationMediaRetentionService:
    def __init__(
        self,
        *,
        storage: ConversationMediaStorage | None = None,
        retention_hours: int | None = None,
    ) -> None:
        self.storage = storage or ConversationMediaStorage()
        self.retention_hours = (
            retention_hours
            if retention_hours is not None
            else settings.conversation_media_retention_hours
        )

    @staticmethod
    def _expired_metadata(
        metadata: dict,
        *,
        now: datetime,
    ) -> dict:
        updated = deepcopy(metadata)

        updated["stored_media"] = False
        updated["media_expired"] = True
        updated["media_expired_at"] = now.isoformat()

        # O histórico textual permanece, mas dados ligados ao arquivo
        # físico deixam de apontar para conteúdo que já foi eliminado.
        updated.pop("stored_media_path", None)
        updated.pop("sha256", None)
        updated.pop("file_size", None)

        return updated

    @staticmethod
    def _restore_staged(
        staged_path: Path,
        original_path: Path,
    ) -> bool:
        if not staged_path.exists():
            return original_path.exists()

        if original_path.exists():
            return False

        try:
            staged_path.rename(original_path)
        except OSError:
            return False

        return True

    def run_once(
        self,
        db: Session,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> ConversationMediaRetentionResult:
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(hours=self.retention_hours)

        messages = list(
            db.scalars(
                select(Message)
                .where(
                    Message.created_at <= cutoff,
                    Message.content_type.in_(["IMAGE", "DOCUMENT"]),
                    Message.metadata_json["stored_media"]
                    .as_boolean()
                    .is_(True),
                )
                .order_by(Message.created_at)
                .limit(limit)
            ).all()
        )

        purged = 0
        files_deleted = 0
        files_missing = 0
        skipped_invalid_path = 0
        file_delete_errors = 0
        file_restore_errors = 0
        db_errors = 0

        for message in messages:
            metadata = deepcopy(message.metadata_json or {})
            relative_path = str(
                metadata.get("stored_media_path") or ""
            ).strip()

            if not relative_path:
                message.metadata_json = self._expired_metadata(
                    metadata,
                    now=current,
                )

                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    db_errors += 1
                    continue

                files_missing += 1
                purged += 1
                continue

            try:
                original_path = self.storage.resolve(relative_path)
            except ConversationMediaStorageError:
                skipped_invalid_path += 1
                continue

            if not original_path.exists():
                message.metadata_json = self._expired_metadata(
                    metadata,
                    now=current,
                )

                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    db_errors += 1
                    continue

                files_missing += 1
                purged += 1
                continue

            if not original_path.is_file():
                skipped_invalid_path += 1
                continue

            staged_path = original_path.with_name(
                f".{original_path.name}.retention-{uuid4().hex}"
            )

            try:
                original_path.rename(staged_path)
            except OSError:
                file_delete_errors += 1
                continue

            message.metadata_json = self._expired_metadata(
                metadata,
                now=current,
            )

            try:
                db.commit()
            except Exception:
                db.rollback()
                db_errors += 1

                if not self._restore_staged(
                    staged_path,
                    original_path,
                ):
                    file_restore_errors += 1

                continue

            try:
                staged_path.unlink()
            except OSError:
                file_delete_errors += 1

                restored = self._restore_staged(
                    staged_path,
                    original_path,
                )

                if not restored:
                    file_restore_errors += 1
                    continue

                try:
                    db.refresh(message)
                    message.metadata_json = metadata
                    db.commit()
                except Exception:
                    db.rollback()
                    db_errors += 1

                continue

            files_deleted += 1
            purged += 1

        return ConversationMediaRetentionResult(
            examined=len(messages),
            purged=purged,
            files_deleted=files_deleted,
            files_missing=files_missing,
            skipped_invalid_path=skipped_invalid_path,
            file_delete_errors=file_delete_errors,
            file_restore_errors=file_restore_errors,
            db_errors=db_errors,
        )
