from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.repositories.channel import ChannelRepository
from app.services.manager_escalation import ManagerEscalationService
from app.services.pix_receipt_review import PixReceiptReviewService


@dataclass(frozen=True)
class PixReviewMonitorResult:
    notified_receipts: int = 0
    notified_staff: int = 0
    rejected_customer_reminders: int = 0
    rejected_staff_alerts: int = 0
    rejected_final_alerts: int = 0


class PixReviewMonitor:
    def __init__(self) -> None:
        self.channels = ChannelRepository()
        self.review = PixReceiptReviewService()
        self.manager = ManagerEscalationService()

    def run_once(
        self,
        db: Session,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> PixReviewMonitorResult:
        current_time = now or datetime.now(timezone.utc)
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

        rejected_customer_reminders = 0
        rejected_staff_alerts = 0
        rejected_final_alerts = 0

        rejected_receipts = list(
            db.scalars(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.status == "HUMAN_REJECTED",
                    PaymentReceipt.order_id.is_not(None),
                    PaymentReceipt.reviewed_at.is_not(None),
                    PaymentReceipt.retention_purged_at.is_(None),
                )
                .order_by(PaymentReceipt.reviewed_at)
                .limit(limit)
            ).all()
        )

        for receipt in rejected_receipts:
            reviewed_at = receipt.reviewed_at
            if reviewed_at is None:
                continue

            if reviewed_at.tzinfo is None:
                reviewed_at = reviewed_at.replace(
                    tzinfo=timezone.utc
                )

            # Qualquer novo comprovante criado depois da rejeição
            # assume o fluxo. O comprovante antigo deixa de gerar
            # lembretes e alertas.
            newer_receipt = db.scalar(
                select(PaymentReceipt.id)
                .where(
                    PaymentReceipt.store_id == receipt.store_id,
                    PaymentReceipt.order_id == receipt.order_id,
                    PaymentReceipt.id != receipt.id,
                    PaymentReceipt.created_at > receipt.reviewed_at,
                )
                .order_by(PaymentReceipt.created_at.desc())
                .limit(1)
            )

            if newer_receipt is not None:
                continue

            age_seconds = (
                current_time - reviewed_at
            ).total_seconds()

            validation = dict(receipt.validation_json or {})

            account = self.channels.get_account_by_store(
                db,
                store_id=receipt.store_id,
                provider="WHATSAPP_CLOUD",
            )

            if account is None:
                continue

            changed = False

            if (
                age_seconds >= 300
                and not validation.get(
                    "rejected_customer_reminded"
                )
            ):
                reminded = self.review.remind_rejected_customer(
                    db,
                    account=account,
                    receipt=receipt,
                )

                if reminded:
                    validation[
                        "rejected_customer_reminded"
                    ] = True
                    rejected_customer_reminders += 1
                    changed = True

            if (
                age_seconds >= 600
                and not validation.get(
                    "rejected_staff_alerted"
                )
            ):
                notified = (
                    self.review.notify_rejected_pending_staff(
                        db,
                        account=account,
                        receipt=receipt,
                    )
                )

                if notified:
                    validation["rejected_staff_alerted"] = True
                    validation[
                        "rejected_staff_alerted_count"
                    ] = notified
                    rejected_staff_alerts += 1
                    changed = True

            if (
                age_seconds >= 900
                and not validation.get(
                    "rejected_staff_final_alerted"
                )
            ):
                order = db.get(
                    Order,
                    receipt.order_id,
                )

                display_id = (
                    order.display_id
                    if order is not None
                    else "não identificado"
                )

                details = (
                    f"O pedido #{display_id} continua aguardando "
                    "um novo comprovante PIX válido. O comprovante "
                    "anterior foi recusado pela equipe e nenhum novo "
                    "comprovante válido foi recebido até agora. "
                    "O pedido permanece pendente e o sistema não "
                    "cancelou o pedido automaticamente."
                )

                if receipt.conversation_id is not None:
                    notified = self.manager.notify_conversation(
                        db,
                        store_id=receipt.store_id,
                        conversation_id=receipt.conversation_id,
                        title="PIX ainda pendente",
                        details=details,
                        source="PIX_REJECTED_15M",
                        now=current_time,
                    )
                else:
                    notified = self.manager.notify_system(
                        db,
                        store_id=receipt.store_id,
                        title="PIX ainda pendente",
                        details=details,
                        source="PIX_REJECTED_15M",
                        now=current_time,
                    )

                if notified:
                    validation[
                        "rejected_staff_final_alerted"
                    ] = True
                    validation[
                        "rejected_staff_final_alerted_count"
                    ] = notified
                    rejected_final_alerts += 1
                    changed = True

            if changed:
                receipt.validation_json = validation
                db.commit()

        return PixReviewMonitorResult(
            notified_receipts=notified_receipts,
            notified_staff=notified_staff,
            rejected_customer_reminders=(
                rejected_customer_reminders
            ),
            rejected_staff_alerts=rejected_staff_alerts,
            rejected_final_alerts=rejected_final_alerts,
        )
