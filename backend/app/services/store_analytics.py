from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem


class StoreAnalyticsService:
    def overview(
        self,
        db: Session,
        *,
        store_id: UUID,
        hours: int = 24,
    ) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)

        period_filter = (
            Order.store_id == store_id,
            Order.created_at >= since,
        )

        valid_filter = (
            *period_filter,
            Order.status != "CANCELLED",
        )

        total_orders = db.scalar(
            select(func.count(Order.id)).where(
                *period_filter,
            )
        ) or 0

        cancelled_orders = db.scalar(
            select(func.count(Order.id)).where(
                *period_filter,
                Order.status == "CANCELLED",
            )
        ) or 0

        valid_row = db.execute(
            select(
                func.count(Order.id),
                func.coalesce(func.sum(Order.total), 0),
                func.count(func.distinct(Order.customer_id)),
            ).where(
                *valid_filter,
            )
        ).one()

        valid_orders = int(valid_row[0] or 0)
        revenue = Decimal(valid_row[1] or 0)
        unique_customers = int(valid_row[2] or 0)

        service_modes = [
            {
                "service_mode": str(service_mode),
                "orders": int(count),
                "revenue": float(Decimal(amount or 0)),
            }
            for service_mode, count, amount in db.execute(
                select(
                    Order.service_mode,
                    func.count(Order.id),
                    func.coalesce(func.sum(Order.total), 0),
                )
                .where(
                    *valid_filter,
                )
                .group_by(Order.service_mode)
                .order_by(func.count(Order.id).desc())
            ).all()
        ]

        payment_methods = [
            {
                "payment_method": str(payment_method),
                "orders": int(count),
                "revenue": float(Decimal(amount or 0)),
            }
            for payment_method, count, amount in db.execute(
                select(
                    Order.payment_method,
                    func.count(Order.id),
                    func.coalesce(func.sum(Order.total), 0),
                )
                .where(
                    *valid_filter,
                )
                .group_by(Order.payment_method)
                .order_by(func.count(Order.id).desc())
            ).all()
        ]

        top_products = [
            {
                "product_id": str(product_id),
                "external_code": external_code,
                "name": name,
                "quantity": int(quantity or 0),
                "revenue": float(Decimal(amount or 0)),
            }
            for (
                product_id,
                external_code,
                name,
                quantity,
                amount,
            ) in db.execute(
                select(
                    OrderItem.product_id,
                    OrderItem.product_external_code,
                    OrderItem.product_name,
                    func.coalesce(func.sum(OrderItem.quantity), 0),
                    func.coalesce(func.sum(OrderItem.total_price), 0),
                )
                .join(
                    Order,
                    Order.id == OrderItem.order_id,
                )
                .where(
                    *valid_filter,
                )
                .group_by(
                    OrderItem.product_id,
                    OrderItem.product_external_code,
                    OrderItem.product_name,
                )
                .order_by(
                    func.sum(OrderItem.quantity).desc(),
                    func.sum(OrderItem.total_price).desc(),
                )
                .limit(10)
            ).all()
        ]

        return {
            "store_id": str(store_id),
            "period_hours": hours,
            "generated_at": now,
            "summary": {
                "orders_total": int(total_orders),
                "orders_valid": valid_orders,
                "orders_cancelled": int(cancelled_orders),
                "revenue": float(revenue),
                "average_ticket": (
                    round(float(revenue / valid_orders), 2)
                    if valid_orders
                    else 0.0
                ),
                "unique_customers": unique_customers,
            },
            "service_modes": service_modes,
            "payment_methods": payment_methods,
            "top_products": top_products,
        }
