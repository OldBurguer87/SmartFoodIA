from __future__ import annotations

import hashlib
import hmac

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.payment import PaymentReceipt


CONFIRMED_RECEIPT_STATUSES = (
    "AUTO_CONFIRMED",
    "HUMAN_CONFIRMED",
)


def transaction_fingerprint(
    transaction_id: str | None,
    secret: str | None,
) -> str | None:
    value = str(transaction_id or "").strip()
    key = str(secret or "").strip()

    if not value or not key:
        return None

    return hmac.new(
        key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def find_duplicate_transaction_receipt(
    db: Session,
    *,
    store_id,
    receipt_id,
    transaction_id: str | None,
    fingerprint_secret: str | None,
) -> PaymentReceipt | None:
    value = str(transaction_id or "").strip()

    if not value:
        return None

    matches = [
        PaymentReceipt.extracted_transaction_id == value,
    ]

    fingerprint = transaction_fingerprint(
        value,
        fingerprint_secret,
    )

    if fingerprint:
        matches.append(
            PaymentReceipt.transaction_fingerprint
            == fingerprint
        )

    return db.scalar(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.store_id == store_id,
            PaymentReceipt.id != receipt_id,
            PaymentReceipt.status.in_(
                CONFIRMED_RECEIPT_STATUSES
            ),
            or_(*matches),
        )
        .limit(1)
    )
