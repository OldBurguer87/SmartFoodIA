from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database.base import Base
from app.models.payment import PaymentReceipt
from app.services.pix_receipt_fingerprint import (
    find_duplicate_transaction_receipt,
    transaction_fingerprint,
)
from app.services.pix_receipt_retention import (
    PixReceiptRetentionService,
)


NOW = datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc)
SECRET = "segredo-de-teste-retencao-pix"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with SessionLocal() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def make_receipt(
    db,
    storage_root: Path,
    *,
    age_days: int,
    transaction_id: str | None = "E2E-TESTE-123",
    status: str = "AUTO_CONFIRMED",
) -> tuple[PaymentReceipt, Path]:
    storage_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path = storage_root / f"{uuid4()}.png"
    file_path.write_bytes(b"comprovante-pix-teste")

    created_at = NOW - timedelta(days=age_days)

    receipt = PaymentReceipt(
        store_id=uuid4(),
        order_id=uuid4(),
        external_media_id="media-sensitive",
        media_type="IMAGE",
        mime_type="image/png",
        original_filename="comprovante-sensitive.png",
        storage_path=str(file_path),
        file_sha256=(uuid4().hex * 2)[:64],
        status=status,
        extracted_receiver_name="Recebedor Sensivel",
        extracted_receiver_document="12345678901",
        extracted_pix_key="pix@sensivel.test",
        extracted_amount=Decimal("10.00"),
        extracted_paid_at=created_at,
        extracted_transaction_id=transaction_id,
        extracted_transaction_status="CONCLUIDO",
        extracted_payer_name="Pagador Sensivel",
        extracted_institution="BANCO SENSIVEL",
        ai_confidence=Decimal("0.9900"),
        validation_json={
            "decision": status,
            "reasons": [],
            "duplicate_file": False,
            "staff_review_notified": True,
            "order_display_id": "000999",
            "candidate_orders": ["000999"],
            "extraction": {
                "payer_name": "Pagador Sensivel",
                "transaction_id": transaction_id,
                "amount": "10.00",
            },
            "checks": {
                "amount_extracted": "10.00",
                "paid_at": created_at.isoformat(),
            },
        },
        reviewed_by="Atendente Teste",
        reviewed_at=created_at + timedelta(minutes=5),
        review_notes="Nota sensivel da revisao",
        created_at=created_at,
        updated_at=created_at,
    )

    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return receipt, file_path


def test_exactly_15_days_is_purged(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=15,
    )

    order_id = receipt.order_id
    original_status = receipt.status
    original_sha = receipt.file_sha256

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.examined == 1
    assert result.purged == 1
    assert result.files_deleted == 1

    assert not file_path.exists()

    assert receipt.order_id == order_id
    assert receipt.status == original_status
    assert receipt.file_sha256 == original_sha

    assert receipt.storage_path is None
    assert receipt.external_media_id is None
    assert receipt.original_filename is None

    assert receipt.extracted_receiver_name is None
    assert receipt.extracted_receiver_document is None
    assert receipt.extracted_pix_key is None
    assert receipt.extracted_amount is None
    assert receipt.extracted_paid_at is None
    assert receipt.extracted_transaction_id is None
    assert receipt.extracted_transaction_status is None
    assert receipt.extracted_payer_name is None
    assert receipt.extracted_institution is None

    assert receipt.ai_confidence is None
    assert receipt.review_notes is None
    assert receipt.retention_purged_at is not None

    assert receipt.transaction_fingerprint == (
        transaction_fingerprint(
            "E2E-TESTE-123",
            SECRET,
        )
    )

    validation = receipt.validation_json

    assert validation["decision"] == original_status
    assert validation["order_display_id"] == "000999"
    assert validation["retention"] == {
        "purged": True,
        "version": 1,
    }

    assert "extraction" not in validation
    assert "checks" not in validation
    assert "candidate_orders" not in validation


def test_14_days_is_not_purged(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=14,
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.examined == 0
    assert result.purged == 0
    assert file_path.exists()
    assert receipt.storage_path is not None
    assert receipt.retention_purged_at is None


def test_missing_file_still_sanitizes_database(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=20,
    )

    file_path.unlink()

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.purged == 1
    assert result.files_missing == 1
    assert receipt.storage_path is None
    assert receipt.extracted_receiver_name is None
    assert receipt.retention_purged_at is not None


def test_missing_secret_blocks_raw_transaction_deletion(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=20,
        transaction_id="E2E-IMPORTANTE-123",
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret="",
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.examined == 1
    assert result.purged == 0
    assert result.skipped_missing_secret == 1

    assert file_path.exists()
    assert receipt.extracted_transaction_id == (
        "E2E-IMPORTANTE-123"
    )
    assert receipt.retention_purged_at is None


def test_missing_transaction_id_does_not_require_secret(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=20,
        transaction_id=None,
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret="",
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.purged == 1
    assert not file_path.exists()
    assert receipt.transaction_fingerprint is None
    assert receipt.retention_purged_at is not None


def test_file_outside_storage_root_is_never_deleted(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, original_file = make_receipt(
        db,
        root,
        age_days=20,
    )

    original_file.unlink()

    outside_file = tmp_path / "fora-da-pasta.png"
    outside_file.write_bytes(b"nao-apagar")

    receipt.storage_path = str(outside_file)
    db.commit()

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.purged == 0
    assert result.skipped_invalid_path == 1
    assert outside_file.exists()
    assert receipt.storage_path == str(outside_file)
    assert receipt.retention_purged_at is None


def test_already_purged_receipt_is_ignored(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=30,
    )

    receipt.retention_purged_at = NOW - timedelta(days=1)
    db.commit()

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    assert result.examined == 0
    assert result.purged == 0
    assert file_path.exists()


def test_transaction_fingerprint_is_stable_and_irreversible() -> None:
    first = transaction_fingerprint(
        "E2E-123456",
        SECRET,
    )

    second = transaction_fingerprint(
        "E2E-123456",
        SECRET,
    )

    other_secret = transaction_fingerprint(
        "E2E-123456",
        "outro-segredo",
    )

    assert first is not None
    assert first == second
    assert first != "E2E-123456"
    assert first != other_secret
    assert len(first) == 64


def test_raw_transaction_id_duplicate_still_works(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    previous, _ = make_receipt(
        db,
        root,
        age_days=1,
        transaction_id="E2E-RAW-123",
    )

    current = PaymentReceipt(
        store_id=previous.store_id,
        external_media_id="media-current",
        media_type="IMAGE",
        storage_path=str(root / "current.png"),
        file_sha256="a" * 64,
        status="RECEIVED",
        extracted_transaction_id="E2E-RAW-123",
    )

    db.add(current)
    db.commit()

    found = find_duplicate_transaction_receipt(
        db,
        store_id=current.store_id,
        receipt_id=current.id,
        transaction_id="E2E-RAW-123",
        fingerprint_secret=SECRET,
    )

    assert found is not None
    assert found.id == previous.id


def test_purged_transaction_is_detected_by_fingerprint(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    previous, _ = make_receipt(
        db,
        root,
        age_days=20,
        transaction_id="E2E-PURGADO-456",
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    assert result.purged == 1

    db.refresh(previous)

    assert previous.extracted_transaction_id is None
    assert previous.transaction_fingerprint is not None

    current = PaymentReceipt(
        store_id=previous.store_id,
        external_media_id="media-current",
        media_type="IMAGE",
        storage_path=str(root / "current.png"),
        file_sha256="b" * 64,
        status="RECEIVED",
        extracted_transaction_id="E2E-PURGADO-456",
    )

    db.add(current)
    db.commit()

    found = find_duplicate_transaction_receipt(
        db,
        store_id=current.store_id,
        receipt_id=current.id,
        transaction_id="E2E-PURGADO-456",
        fingerprint_secret=SECRET,
    )

    assert found is not None
    assert found.id == previous.id


def test_transaction_fingerprint_is_isolated_by_store(
    db,
    tmp_path: Path,
) -> None:
    root = tmp_path / "receipts"

    previous, _ = make_receipt(
        db,
        root,
        age_days=20,
        transaction_id="E2E-STORE-789",
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    service.run_once(
        db,
        now=NOW,
    )

    found = find_duplicate_transaction_receipt(
        db,
        store_id=uuid4(),
        receipt_id=uuid4(),
        transaction_id="E2E-STORE-789",
        fingerprint_secret=SECRET,
    )

    assert found is None


def test_file_delete_error_does_not_stop_other_receipts(
    db,
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "receipts"

    bad_receipt, bad_file = make_receipt(
        db,
        root,
        age_days=30,
        transaction_id="E2E-ERRO-ARQUIVO",
    )

    good_receipt, good_file = make_receipt(
        db,
        root,
        age_days=20,
        transaction_id="E2E-ARQUIVO-OK",
    )

    original_unlink = Path.unlink

    def controlled_unlink(self, *args, **kwargs):
        if (
            bad_file.name in self.name
            and ".retention-" in self.name
        ):
            raise PermissionError("erro de disco simulado")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(
        Path,
        "unlink",
        controlled_unlink,
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(bad_receipt)
    db.refresh(good_receipt)

    assert result.examined == 2
    assert result.file_delete_errors == 1
    assert result.purged == 1

    assert bad_file.exists()
    assert bad_receipt.storage_path is not None
    assert bad_receipt.retention_purged_at is None

    assert not good_file.exists()
    assert good_receipt.storage_path is None
    assert good_receipt.retention_purged_at is not None


def test_db_commit_failure_restores_file_and_database(
    db,
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "receipts"

    receipt, file_path = make_receipt(
        db,
        root,
        age_days=20,
        transaction_id="E2E-COMMIT-FAIL",
    )

    original_commit = db.commit
    calls = {"count": 0}

    def fail_first_commit():
        calls["count"] += 1

        if calls["count"] == 1:
            raise RuntimeError(
                "falha de banco simulada"
            )

        return original_commit()

    monkeypatch.setattr(
        db,
        "commit",
        fail_first_commit,
    )

    service = PixReceiptRetentionService(
        storage_root=root,
        retention_days=15,
        fingerprint_secret=SECRET,
    )

    result = service.run_once(
        db,
        now=NOW,
    )

    db.refresh(receipt)

    assert result.examined == 1
    assert result.purged == 0
    assert result.db_errors == 1
    assert result.file_restore_errors == 0

    assert file_path.exists()

    assert receipt.storage_path == str(file_path)
    assert receipt.external_media_id == "media-sensitive"
    assert receipt.extracted_transaction_id == (
        "E2E-COMMIT-FAIL"
    )
    assert receipt.transaction_fingerprint is None
    assert receipt.retention_purged_at is None

    staged = list(
        root.glob(
            f".{file_path.name}.retention-*"
        )
    )
    assert staged == []
