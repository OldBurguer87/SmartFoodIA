from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.payment import PaymentReceipt
from app.repositories.channel import ChannelRepository
from app.services.pix_receipt_review import PixReceiptReviewService


@dataclass(frozen=True)
class PixReviewMonitorResult:
    notified_receipts: int = 0
    notified_staff: int = 0


class PixReviewMonitor:
    def __init__(self) -> None:
        self.channels = ChannelRepository()
        self.review = PixReceiptReviewService()

    def run_once(
        self,
        db: Session,
        *,
        limit: int = 50,
    ) -> PixReviewMonitorResult:
        notified_flag = PaymentReceipt.validation_json.op("->>")(
            "staff_review_notified"
        )

        receipts = list(
            db.scalars(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.status == "NEEDS_REVIEW",
                    PaymentReceipt.order_id.is_not(None),
                    PaymentReceipt.retention_purged_at.is_(None),
                    or_(
                        notified_flag.is_(None),
                        notified_flag != "true",
                    ),
                )
                .order_by(PaymentReceipt.created_at)
                .limit(limit)
            ).all()
        )

        notified_receipts = 0
        notified_staff = 0

        for receipt in receipts:
            validation = receipt.validation_json or {}

            if bool(validation.get("staff_review_notified")):
                continue

            account = self.channels.get_account_by_store(
                db,
                store_id=receipt.store_id,
                provider="WHATSAPP_CLOUD",
            )

            if account is None:
                continue

            notified = self.review.notify_review(
                db,
                account=account,
                receipt=receipt,
            )

            if not notified:
                continue

            receipt.validation_json = {
                **validation,
                "staff_review_notified": True,
                "staff_review_notified_count": notified,
            }

            db.commit()

            notified_receipts += 1
            notified_staff += notified

        return PixReviewMonitorResult(
            notified_receipts=notified_receipts,
            notified_staff=notified_staff,
        )
