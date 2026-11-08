from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Store
from app.models.commercial import StoreBusinessHours
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.services.order_payments import payment_amount, payment_parts_from_order


class ShiftClosingService:
    """Fechamento financeiro por turno comercial."""

    def shift_bounds(
        self,
        db: Session,
        *,
        store_id: UUID,
        shift_date: date,
    ) -> tuple[datetime, datetime] | None:
        store = db.get(Store, store_id)
        if store is None:
            raise LookupError("Loja não encontrada.")

        hours = db.scalar(
            select(StoreBusinessHours).where(
                StoreBusinessHours.store_id == store_id,
                StoreBusinessHours.weekday == shift_date.weekday(),
            )
        )

        if (
            hours is None
            or hours.closed
            or hours.open_time is None
            or hours.close_time is None
        ):
            return None

        local_tz = ZoneInfo(store.timezone)
        start_local = datetime.combine(
            shift_date,
            hours.open_time,
            tzinfo=local_tz,
        )

        end_date = shift_date
        if hours.open_time > hours.close_time:
            end_date += timedelta(days=1)

        end_local = datetime.combine(
            end_date,
            hours.close_time,
            tzinfo=local_tz,
        )

        return start_local, end_local

    def order_summary(
        self,
        db: Session,
        *,
        store_id: UUID,
        shift_date: date,
    ) -> dict:
        from collections import Counter
        from datetime import timezone
        from app.models.order import Order

        bounds = self.shift_bounds(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        if bounds is None:
            return {
                "total": 0,
                "valid": 0,
                "cancelled": 0,
                "by_status": {},
            }

        start_local, end_local = bounds
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        orders = list(
            db.scalars(
                select(Order).where(
                    Order.store_id == store_id,
                    Order.created_at >= start_utc,
                    Order.created_at <= end_utc,
                )
            ).all()
        )

        statuses = Counter(
            str(order.status).upper()
            for order in orders
        )

        cancelled = statuses.get("CANCELLED", 0)

        return {
            "total": len(orders),
            "valid": len(orders) - cancelled,
            "cancelled": cancelled,
            "by_status": dict(sorted(statuses.items())),
        }

    def financial_summary(
        self,
        db: Session,
        *,
        store_id: UUID,
        shift_date: date,
    ) -> dict:
        from datetime import timezone
        from decimal import Decimal

        bounds = self.shift_bounds(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        if bounds is None:
            return {
                "revenue": 0.0,
                "average_ticket": 0.0,
                "valid_orders": 0,
                "payment_total": 0.0,
                "difference": 0.0,
                "payment_methods": [],
            }

        start_local, end_local = bounds

        orders = list(
            db.scalars(
                select(Order)
                .where(
                    Order.store_id == store_id,
                    Order.created_at >= start_local.astimezone(timezone.utc),
                    Order.created_at <= end_local.astimezone(timezone.utc),
                    Order.status != "CANCELLED",
                )
                .options(selectinload(Order.payments))
            ).all()
        )

        revenue = sum(
            (Decimal(str(order.total)) for order in orders),
            Decimal("0.00"),
        )

        totals: dict[str, Decimal] = {}
        order_ids: dict[str, set] = {}

        for order in orders:
            for part in payment_parts_from_order(order):
                method = str(part.method).upper()
                amount = Decimal(str(part.amount))
                totals[method] = totals.get(method, Decimal("0.00")) + amount
                order_ids.setdefault(method, set()).add(order.id)

        payment_total = sum(totals.values(), Decimal("0.00"))
        difference = revenue - payment_total
        average_ticket = (
            revenue / len(orders)
            if orders
            else Decimal("0.00")
        )

        methods = [
            {
                "method": method,
                "orders": len(order_ids[method]),
                "amount": float(amount.quantize(Decimal("0.01"))),
            }
            for method, amount in sorted(
                totals.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

        return {
            "revenue": float(revenue.quantize(Decimal("0.01"))),
            "average_ticket": float(average_ticket.quantize(Decimal("0.01"))),
            "valid_orders": len(orders),
            "payment_total": float(payment_total.quantize(Decimal("0.01"))),
            "difference": float(difference.quantize(Decimal("0.01"))),
            "payment_methods": methods,
        }

    def pix_summary(
        self,
        db: Session,
        *,
        store_id: UUID,
        shift_date: date,
    ) -> dict:
        from datetime import timezone
        from decimal import Decimal

        bounds = self.shift_bounds(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        if bounds is None:
            return {
                "orders": 0,
                "amount": 0.0,
                "confirmed_orders": 0,
                "confirmed_amount": 0.0,
                "auto_confirmed": 0,
                "human_confirmed": 0,
                "pending_review": 0,
                "without_receipt": 0,
                "fallback_values": 0,
            }

        start_local, end_local = bounds
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        receipt_cutoff = (
            end_local + timedelta(minutes=5)
        ).astimezone(timezone.utc)

        orders = list(
            db.scalars(
                select(Order)
                .where(
                    Order.store_id == store_id,
                    Order.created_at >= start_utc,
                    Order.created_at <= end_utc,
                    Order.status != "CANCELLED",
                )
                .options(selectinload(Order.payments))
            ).all()
        )

        pix_orders = {}
        pix_total = Decimal("0.00")

        for order in orders:
            amount = payment_amount(order, "PIX")
            if amount is not None and amount > 0:
                pix_orders[order.id] = (order, Decimal(amount))
                pix_total += Decimal(amount)

        confirmed = {}
        pending = set()
        orders_with_receipt = set()

        if pix_orders:
            receipts = list(
                db.scalars(
                    select(PaymentReceipt)
                    .where(
                        PaymentReceipt.store_id == store_id,
                        PaymentReceipt.order_id.in_(list(pix_orders)),
                        PaymentReceipt.created_at <= receipt_cutoff,
                    )
                    .order_by(
                        PaymentReceipt.created_at,
                        PaymentReceipt.id,
                    )
                ).all()
            )

            for receipt in receipts:
                order_id = receipt.order_id
                orders_with_receipt.add(order_id)

                if receipt.status in {"AUTO_CONFIRMED", "HUMAN_CONFIRMED"}:
                    confirmed[order_id] = receipt
                    pending.discard(order_id)
                elif (
                    receipt.status == "NEEDS_REVIEW"
                    and order_id not in confirmed
                ):
                    pending.add(order_id)

        confirmed_amount = Decimal("0.00")
        auto_confirmed = 0
        human_confirmed = 0
        fallback_values = 0

        for order_id, receipt in confirmed.items():
            order, order_pix = pix_orders[order_id]

            if receipt.extracted_amount is not None:
                amount = Decimal(receipt.extracted_amount)
            else:
                amount = order_pix
                fallback_values += 1

            confirmed_amount += amount

            if receipt.status == "AUTO_CONFIRMED":
                auto_confirmed += 1
            else:
                human_confirmed += 1

        without_receipt = len(
            set(pix_orders) - orders_with_receipt
        )

        return {
            "orders": len(pix_orders),
            "amount": float(pix_total.quantize(Decimal("0.01"))),
            "confirmed_orders": len(confirmed),
            "confirmed_amount": float(confirmed_amount.quantize(Decimal("0.01"))),
            "auto_confirmed": auto_confirmed,
            "human_confirmed": human_confirmed,
            "pending_review": len(pending),
            "without_receipt": without_receipt,
            "fallback_values": fallback_values,
        }

    def build_report(
        self,
        db: Session,
        *,
        store_id: UUID,
        shift_date: date,
    ) -> dict:
        store = db.get(Store, store_id)
        if store is None:
            raise LookupError("Loja não encontrada.")

        bounds = self.shift_bounds(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        orders = self.order_summary(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        financial = self.financial_summary(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        pix = self.pix_summary(
            db,
            store_id=store_id,
            shift_date=shift_date,
        )

        return {
            "store_id": str(store.id),
            "store_name": store.name,
            "shift_date": shift_date.isoformat(),
            "configured": bounds is not None,
            "started_at": bounds[0].isoformat() if bounds else None,
            "ends_at": bounds[1].isoformat() if bounds else None,
            "orders": orders,
            "financial": financial,
            "pix": pix,
        }
