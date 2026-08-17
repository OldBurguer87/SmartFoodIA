from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import PaymentReceipt
from app.services.pix_receipt_fingerprint import (
    transaction_fingerprint,
)


@dataclass(frozen=True)
class PixReceiptRetentionResult:
    examined: int = 0
    purged: int = 0
    files_deleted: int = 0
    files_missing: int = 0
    skipped_missing_secret: int = 0
    skipped_invalid_path: int = 0
    file_delete_errors: int = 0
    file_restore_errors: int = 0
    db_errors: int = 0


@dataclass
class _PreparedPurge:
    receipt: PaymentReceipt
    file_state: str
    original_path: Path | None
    staged_path: Path | None
    snapshot: dict[str, object]


class PixReceiptRetentionService:
    def __init__(
        self,
        *,
        storage_root: str | Path | None = None,
        retention_days: int | None = None,
        fingerprint_secret: str | None = None,
    ) -> None:
        self.storage_root = Path(
            storage_root
            or settings.payment_receipt_storage_path
        )

        self.retention_days = (
            retention_days
            if retention_days is not None
            else settings.payment_receipt_retention_days
        )

        self.fingerprint_secret = (
            fingerprint_secret
            if fingerprint_secret is not None
            else settings.pix_receipt_fingerprint_secret
        )

    @staticmethod
    def _sanitized_validation(
        receipt: PaymentReceipt,
    ) -> dict:
        current = receipt.validation_json or {}
        safe: dict[str, object] = {}

        for key in (
            "decision",
            "reasons",
            "duplicate_file",
            "duplicate_receipt_id",
            "staff_review_notified",
            "staff_review_notified_count",
            "order_display_id",
        ):
            if key in current:
                safe[key] = current[key]

        safe["retention"] = {
            "purged": True,
            "version": 1,
        }

        return safe

    @staticmethod
    def _snapshot(
        receipt: PaymentReceipt,
    ) -> dict[str, object]:
        fields = (
            "transaction_fingerprint",
            "external_media_id",
            "original_filename",
            "storage_path",
            "extracted_receiver_name",
            "extracted_receiver_document",
            "extracted_pix_key",
            "extracted_amount",
            "extracted_paid_at",
            "extracted_transaction_id",
            "extracted_transaction_status",
            "extracted_payer_name",
            "extracted_institution",
            "ai_confidence",
            "review_notes",
            "validation_json",
            "retention_purged_at",
        )

        return {
            field: deepcopy(getattr(receipt, field))
            for field in fields
        }

    @staticmethod
    def _restore_snapshot(
        prepared: _PreparedPurge,
        *,
        storage_path_override: str | None = None,
    ) -> None:
        for field, value in prepared.snapshot.items():
            setattr(
                prepared.receipt,
                field,
                deepcopy(value),
            )

        if storage_path_override is not None:
            prepared.receipt.storage_path = (
                storage_path_override
            )

    def _managed_path(
        self,
        storage_path: str,
    ) -> Path | None:
        root = self.storage_root.resolve()
        candidate = Path(storage_path).resolve()

        try:
            candidate.relative_to(root)
        except ValueError:
            return None

        return candidate

    def _stage_file(
        self,
        receipt: PaymentReceipt,
    ) -> tuple[str, Path | None, Path | None]:
        if not receipt.storage_path:
            return "NONE", None, None

        file_path = self._managed_path(
            receipt.storage_path
        )

        if file_path is None:
            return "INVALID_PATH", None, None

        if not file_path.exists():
            return "MISSING", file_path, None

        if not file_path.is_file():
            return "INVALID_PATH", None, None

        staged_path = file_path.with_name(
            f".{file_path.name}.retention-{uuid4().hex}"
        )

        file_path.rename(staged_path)

        return "STAGED", file_path, staged_path

    @staticmethod
    def _restore_staged_file(
        prepared: _PreparedPurge,
    ) -> tuple[bool, Path | None]:
        staged = prepared.staged_path
        original = prepared.original_path

        if staged is None:
            return True, None

        if not staged.exists():
            if original is not None and original.exists():
                return True, None
            return False, None

        if original is None:
            return False, staged

        if original.exists():
            return False, staged

        try:
            staged.rename(original)
        except OSError:
            if staged.exists():
                return False, staged
            return False, None

        return True, None

    def purge_receipt(
        self,
        receipt: PaymentReceipt,
        *,
        now: datetime | None = None,
    ) -> str | _PreparedPurge:
        current = now or datetime.now(timezone.utc)

        transaction_id = str(
            receipt.extracted_transaction_id or ""
        ).strip()

        fingerprint = transaction_fingerprint(
            transaction_id,
            self.fingerprint_secret,
        )

        # Nunca apagar o E2E bruto sem antes criar sua
        # representação irreversível para antifraude.
        if transaction_id and fingerprint is None:
            return "MISSING_SECRET"

        snapshot = self._snapshot(receipt)

        file_state, original_path, staged_path = (
            self._stage_file(receipt)
        )

        if file_state == "INVALID_PATH":
            return "INVALID_PATH"

        receipt.transaction_fingerprint = fingerprint

        receipt.external_media_id = None
        receipt.original_filename = None
        receipt.storage_path = None

        receipt.extracted_receiver_name = None
        receipt.extracted_receiver_document = None
        receipt.extracted_pix_key = None
        receipt.extracted_amount = None
        receipt.extracted_paid_at = None
        receipt.extracted_transaction_id = None
        receipt.extracted_transaction_status = None
        receipt.extracted_payer_name = None
        receipt.extracted_institution = None

        receipt.ai_confidence = None
        receipt.review_notes = None
        receipt.validation_json = (
            self._sanitized_validation(receipt)
        )
        receipt.retention_purged_at = current

        return _PreparedPurge(
            receipt=receipt,
            file_state=file_state,
            original_path=original_path,
            staged_path=staged_path,
            snapshot=snapshot,
        )

    def run_once(
        self,
        db: Session,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> PixReceiptRetentionResult:
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(
            days=self.retention_days
        )

        receipts = list(
            db.scalars(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.created_at <= cutoff,
                    PaymentReceipt.retention_purged_at.is_(
                        None
                    ),
                )
                .order_by(PaymentReceipt.created_at)
                .limit(limit)
            ).all()
        )

        purged = 0
        files_deleted = 0
        files_missing = 0
        skipped_missing_secret = 0
        skipped_invalid_path = 0
        file_delete_errors = 0
        file_restore_errors = 0
        db_errors = 0

        for receipt in receipts:
            try:
                prepared = self.purge_receipt(
                    receipt,
                    now=current,
                )
            except OSError:
                db.rollback()
                file_delete_errors += 1
                continue

            if prepared == "MISSING_SECRET":
                skipped_missing_secret += 1
                continue

            if prepared == "INVALID_PATH":
                skipped_invalid_path += 1
                continue

            assert isinstance(
                prepared,
                _PreparedPurge,
            )

            try:
                db.commit()
            except Exception:
                db.rollback()
                db_errors += 1

                restored, recovery_path = (
                    self._restore_staged_file(
                        prepared
                    )
                )

                if not restored:
                    file_restore_errors += 1

                    if recovery_path is not None:
                        try:
                            db.refresh(receipt)
                            receipt.storage_path = str(
                                recovery_path
                            )
                            db.commit()
                        except Exception:
                            db.rollback()
                            db_errors += 1

                continue

            if prepared.file_state == "STAGED":
                staged = prepared.staged_path

                assert staged is not None

                try:
                    staged.unlink()
                except OSError:
                    file_delete_errors += 1

                    restored, recovery_path = (
                        self._restore_staged_file(
                            prepared
                        )
                    )

                    if not restored:
                        file_restore_errors += 1

                    if restored:
                        override = None
                    elif recovery_path is not None:
                        override = str(recovery_path)
                    else:
                        # O arquivo não existe mais em nenhum
                        # dos dois caminhos. O banco já está
                        # purgado, então não há prova física
                        # conhecida para restaurar.
                        purged += 1
                        continue

                    self._restore_snapshot(
                        prepared,
                        storage_path_override=override,
                    )

                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                        db_errors += 1

                    continue

                files_deleted += 1

            elif prepared.file_state == "MISSING":
                files_missing += 1

            purged += 1

        return PixReceiptRetentionResult(
            examined=len(receipts),
            purged=purged,
            files_deleted=files_deleted,
            files_missing=files_missing,
            skipped_missing_secret=(
                skipped_missing_secret
            ),
            skipped_invalid_path=(
                skipped_invalid_path
            ),
            file_delete_errors=file_delete_errors,
            file_restore_errors=file_restore_errors,
            db_errors=db_errors,
        )
