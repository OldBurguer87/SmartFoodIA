from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Store
from app.models.channel import OutboundChannelMessage
from app.models.commercial import StoreBusinessHours
from app.models.order import Order, OrderPayment
from app.models.payment import PaymentReceipt
from app.models.staff import StoreStaffMember
from app.repositories.channel import ChannelRepository
from app.services.order_payments import payment_amount


CONFIRMED_RECEIPT_STATUSES = {
    "AUTO_CONFIRMED",
    "HUMAN_CONFIRMED",
}

PENDING_RECEIPT_STATUS = "NEEDS_REVIEW"


@dataclass(frozen=True)
class PixShiftSummary:
    shift_date: date
    start_local: datetime
    end_local: datetime
    confirmed_orders: int
    auto_confirmed: int
    human_confirmed: int
    pending_review: int
    fallback_values: int
    total: Decimal


@dataclass(frozen=True)
class PixShiftClosingResult:
    shift_date: date | None = None
    queued_messages: int = 0
    already_queued: int = 0
    recipients: int = 0
    total: Decimal = Decimal("0.00")


class PixShiftClosingService:
    """
    Envia o fechamento PIX da Old Burguer 87 após o encerramento
    do turno.

    Idempotência:
    cada fechamento possui uma referência única por data.
    Antes de enfileirar uma mensagem, a fila outbound é consultada
    para verificar se aquele destinatário já recebeu o fechamento.

    Se o worker reiniciar entre um destinatário e outro, a mensagem
    já criada serve também como snapshot canônico do fechamento.
    """

    STORE_SLUG = "old-burguer-87"
    PROVIDER = "WHATSAPP_CLOUD"

    # Aguarda alguns minutos após o fechamento para permitir que
    # comprovantes recebidos no fim do turno terminem de ser analisados.
    GRACE_MINUTES = 5

    # Permite recuperar o fechamento após uma indisponibilidade curta,
    # sem começar a disparar fechamentos históricos antigos.
    CATCHUP_HOURS = 12

    def __init__(self) -> None:
        self.channels = ChannelRepository()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_money(value: Decimal) -> str:
        formatted = f"{value:,.2f}"
        formatted = (
            formatted
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        return f"R$ {formatted}"

    @staticmethod
    def _shift_bounds(
        *,
        shift_date: date,
        hours: StoreBusinessHours,
        tz: ZoneInfo,
    ) -> tuple[datetime, datetime]:
        start_local = datetime.combine(
            shift_date,
            hours.open_time,
            tzinfo=tz,
        )
        end_local = datetime.combine(
            shift_date,
            hours.close_time,
            tzinfo=tz,
        )

        if hours.close_time < hours.open_time:
            end_local += timedelta(days=1)

        return start_local, end_local

    def _find_due_shift(
        self,
        db: Session,
        *,
        store: Store,
        now: datetime,
    ) -> tuple[date, StoreBusinessHours, datetime, datetime] | None:
        tz = ZoneInfo(store.timezone)
        now_utc = self._as_utc(now)
        local_now = now_utc.astimezone(tz)

        candidates = (
            local_now.date(),
            local_now.date() - timedelta(days=1),
        )

        for shift_date in candidates:
            hours = db.scalar(
                select(StoreBusinessHours).where(
                    StoreBusinessHours.store_id == store.id,
                    StoreBusinessHours.weekday
                    == shift_date.weekday(),
                )
            )

            if (
                hours is None
                or hours.closed
                or hours.open_time is None
                or hours.close_time is None
            ):
                continue

            start_local, end_local = self._shift_bounds(
                shift_date=shift_date,
                hours=hours,
                tz=tz,
            )

            send_after = end_local + timedelta(
                minutes=self.GRACE_MINUTES
            )

            if local_now < send_after:
                continue

            if (
                local_now - send_after
                > timedelta(hours=self.CATCHUP_HOURS)
            ):
                continue

            return (
                shift_date,
                hours,
                start_local,
                end_local,
            )

        return None

    def build_summary(
        self,
        db: Session,
        *,
        store_id: UUID,
        shift_date: date,
        start_local: datetime,
        end_local: datetime,
    ) -> PixShiftSummary:
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        receipt_cutoff_utc = (
            end_local
            + timedelta(minutes=self.GRACE_MINUTES)
        ).astimezone(timezone.utc)

        rows = db.execute(
            select(PaymentReceipt, Order)
            .join(
                Order,
                Order.id == PaymentReceipt.order_id,
            )
            .where(
                PaymentReceipt.store_id == store_id,
                Order.store_id == store_id,
                Order.created_at >= start_utc,
                Order.created_at <= end_utc,
                PaymentReceipt.created_at <= receipt_cutoff_utc,
                or_(
                    Order.payment_method == "PIX",
                    select(OrderPayment.id)
                    .where(
                        OrderPayment.order_id == Order.id,
                        OrderPayment.method == "PIX",
                    )
                    .exists(),
                ),
            )
            .options(selectinload(Order.payments))
            .order_by(
                PaymentReceipt.created_at,
                PaymentReceipt.id,
            )
        ).all()

        confirmed_by_order: dict[
            UUID,
            tuple[PaymentReceipt, Order],
        ] = {}

        pending_orders: set[UUID] = set()

        for receipt, order in rows:
            if receipt.status in CONFIRMED_RECEIPT_STATUSES:
                confirmed_by_order[order.id] = (
                    receipt,
                    order,
                )
                pending_orders.discard(order.id)
                continue

            if (
                receipt.status == PENDING_RECEIPT_STATUS
                and order.id not in confirmed_by_order
            ):
                pending_orders.add(order.id)

        total = Decimal("0.00")
        auto_confirmed = 0
        human_confirmed = 0
        fallback_values = 0

        for receipt, order in confirmed_by_order.values():
            if receipt.extracted_amount is not None:
                amount = Decimal(receipt.extracted_amount)
            else:
                amount = payment_amount(order, "PIX")

                if amount is None:
                    continue

                fallback_values += 1

            total += amount

            if receipt.status == "AUTO_CONFIRMED":
                auto_confirmed += 1
            else:
                human_confirmed += 1

        return PixShiftSummary(
            shift_date=shift_date,
            start_local=start_local,
            end_local=end_local,
            confirmed_orders=len(confirmed_by_order),
            auto_confirmed=auto_confirmed,
            human_confirmed=human_confirmed,
            pending_review=len(pending_orders),
            fallback_values=fallback_values,
            total=total.quantize(Decimal("0.01")),
        )

    @staticmethod
    def reference(shift_date: date) -> str:
        return (
            "PIX-SHIFT-"
            + shift_date.strftime("%Y%m%d")
        )

    def format_message(
        self,
        *,
        store: Store,
        summary: PixShiftSummary,
    ) -> str:
        lines = [
            f"📊 FECHAMENTO PIX — {store.name.upper()}",
            "",
            (
                "Turno: "
                f"{summary.shift_date.strftime('%d/%m/%Y')} — "
                f"{summary.start_local.strftime('%H:%M')} às "
                f"{summary.end_local.strftime('%H:%M')}"
            ),
            "",
            f"PIX confirmados: {summary.confirmed_orders}",
            f"• Automáticos: {summary.auto_confirmed}",
            (
                "• Confirmados pela equipe: "
                f"{summary.human_confirmed}"
            ),
            "",
            (
                "Total PIX recebido: "
                f"{self._format_money(summary.total)}"
            ),
            "",
            (
                "Pendentes de conferência: "
                f"{summary.pending_review}"
            ),
        ]

        if summary.fallback_values:
            lines.extend(
                [
                    "",
                    (
                        "ℹ️ "
                        f"{summary.fallback_values} valor(es) "
                        "confirmado(s) manualmente foram "
                        "contabilizados pelo total do pedido."
                    ),
                ]
            )

        lines.extend(
            [
                "",
                (
                    "Ref. fechamento: "
                    f"{self.reference(summary.shift_date)}"
                ),
            ]
        )

        return "\n".join(lines)

    def _recipients(
        self,
        db: Session,
        *,
        store_id: UUID,
    ) -> list[StoreStaffMember]:
        return list(
            db.scalars(
                select(StoreStaffMember)
                .where(
                    StoreStaffMember.store_id == store_id,
                    StoreStaffMember.active.is_(True),
                    StoreStaffMember.notify_whatsapp.is_(True),
                )
                .order_by(
                    StoreStaffMember.created_at,
                    StoreStaffMember.id,
                )
            ).all()
        )

    def _existing_snapshot(
        self,
        db: Session,
        *,
        account_id: UUID,
        marker: str,
    ) -> OutboundChannelMessage | None:
        return db.scalar(
            select(OutboundChannelMessage)
            .where(
                OutboundChannelMessage.channel_account_id
                == account_id,
                OutboundChannelMessage.content.contains(
                    marker
                ),
            )
            .order_by(OutboundChannelMessage.created_at)
            .limit(1)
        )

    def _already_queued_for_recipient(
        self,
        db: Session,
        *,
        account_id: UUID,
        recipient: str,
        marker: str,
    ) -> bool:
        existing = db.scalar(
            select(OutboundChannelMessage.id)
            .where(
                OutboundChannelMessage.channel_account_id
                == account_id,
                OutboundChannelMessage.recipient
                == recipient,
                OutboundChannelMessage.content.contains(
                    marker
                ),
            )
            .limit(1)
        )
        return existing is not None

    def run_once(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> PixShiftClosingResult:
        current = now or datetime.now(timezone.utc)

        store = db.scalar(
            select(Store).where(
                Store.slug == self.STORE_SLUG
            )
        )

        if store is None:
            return PixShiftClosingResult()

        due = self._find_due_shift(
            db,
            store=store,
            now=current,
        )

        if due is None:
            return PixShiftClosingResult()

        (
            shift_date,
            _hours,
            start_local,
            end_local,
        ) = due

        account = self.channels.get_account_by_store(
            db,
            store_id=store.id,
            provider=self.PROVIDER,
        )

        if account is None:
            return PixShiftClosingResult(
                shift_date=shift_date,
            )

        recipients = self._recipients(
            db,
            store_id=store.id,
        )

        if not recipients:
            return PixShiftClosingResult(
                shift_date=shift_date,
            )

        marker = self.reference(shift_date)

        # Se uma mensagem deste fechamento já foi criada,
        # reutilizamos exatamente o mesmo conteúdo para todos.
        # Isso mantém o snapshot financeiro idêntico mesmo
        # se o worker reiniciar durante o envio.
        snapshot = self._existing_snapshot(
            db,
            account_id=account.id,
            marker=marker,
        )

        if snapshot is not None:
            message = snapshot.content
            total = Decimal("0.00")
        else:
            summary = self.build_summary(
                db,
                store_id=store.id,
                shift_date=shift_date,
                start_local=start_local,
                end_local=end_local,
            )
            message = self.format_message(
                store=store,
                summary=summary,
            )
            total = summary.total

        queued = 0
        already = 0

        for member in recipients:
            if self._already_queued_for_recipient(
                db,
                account_id=account.id,
                recipient=member.phone,
                marker=marker,
            ):
                already += 1
                continue

            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=None,
                recipient=member.phone,
                content=message,
            )
            queued += 1

        return PixShiftClosingResult(
            shift_date=shift_date,
            queued_messages=queued,
            already_queued=already,
            recipients=len(recipients),
            total=total,
        )
