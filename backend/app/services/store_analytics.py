from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.order import (
    Order,
    OrderItem,
    OrderItemModifier,
)


class StoreAnalyticsService:
    WEEKDAY_LABELS = (
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    )

    def overview(
        self,
        db: Session,
        *,
        store_id: UUID,
        hours: int = 24,
    ) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)

        store = db.get(
            Store,
            store_id,
        )

        store_timezone = self._timezone(
            store.timezone if store else "UTC",
        )

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
                func.count(
                    func.distinct(Order.customer_id),
                ),
            ).where(
                *valid_filter,
            )
        ).one()

        valid_orders = int(valid_row[0] or 0)
        revenue = Decimal(valid_row[1] or 0)
        unique_customers = int(valid_row[2] or 0)

        customer_segments = self._customer_segments(
            db,
            store_id=store_id,
            since=since,
            valid_filter=valid_filter,
        )

        service_modes = [
            {
                "service_mode": str(service_mode),
                "orders": int(count),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for service_mode, count, amount in db.execute(
                select(
                    Order.service_mode,
                    func.count(Order.id),
                    func.coalesce(
                        func.sum(Order.total),
                        0,
                    ),
                )
                .where(
                    *valid_filter,
                )
                .group_by(
                    Order.service_mode,
                )
                .order_by(
                    func.count(Order.id).desc(),
                )
            ).all()
        ]

        payment_methods = [
            {
                "payment_method": str(payment_method),
                "orders": int(count),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for payment_method, count, amount in db.execute(
                select(
                    Order.payment_method,
                    func.count(Order.id),
                    func.coalesce(
                        func.sum(Order.total),
                        0,
                    ),
                )
                .where(
                    *valid_filter,
                )
                .group_by(
                    Order.payment_method,
                )
                .order_by(
                    func.count(Order.id).desc(),
                )
            ).all()
        ]

        top_products = [
            {
                "product_id": str(product_id),
                "external_code": external_code,
                "name": name,
                "quantity": int(quantity or 0),
                "revenue": float(
                    Decimal(amount or 0)
                ),
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
                    func.coalesce(
                        func.sum(OrderItem.quantity),
                        0,
                    ),
                    func.coalesce(
                        func.sum(OrderItem.total_price),
                        0,
                    ),
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
                    func.sum(
                        OrderItem.quantity
                    ).desc(),
                    func.sum(
                        OrderItem.total_price
                    ).desc(),
                )
                .limit(10)
            ).all()
        ]

        top_modifiers = [
            {
                "modifier_id": str(modifier_id),
                "external_code": external_code,
                "name": name,
                "quantity": int(quantity or 0),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for (
                modifier_id,
                external_code,
                name,
                quantity,
                amount,
            ) in db.execute(
                select(
                    OrderItemModifier.modifier_id,
                    OrderItemModifier.modifier_external_code,
                    OrderItemModifier.modifier_name,
                    func.coalesce(
                        func.sum(
                            OrderItemModifier.quantity
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            OrderItemModifier.total_price
                        ),
                        0,
                    ),
                )
                .join(
                    OrderItem,
                    OrderItem.id
                    == OrderItemModifier.order_item_id,
                )
                .join(
                    Order,
                    Order.id == OrderItem.order_id,
                )
                .where(
                    *valid_filter,
                )
                .group_by(
                    OrderItemModifier.modifier_id,
                    OrderItemModifier.modifier_external_code,
                    OrderItemModifier.modifier_name,
                )
                .order_by(
                    func.sum(
                        OrderItemModifier.quantity
                    ).desc(),
                    func.sum(
                        OrderItemModifier.total_price
                    ).desc(),
                )
                .limit(10)
            ).all()
        ]

        top_neighborhoods = [
            {
                "neighborhood": neighborhood,
                "orders": int(count),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for neighborhood, count, amount in db.execute(
                select(
                    Order.address_neighborhood,
                    func.count(Order.id),
                    func.coalesce(
                        func.sum(Order.total),
                        0,
                    ),
                )
                .where(
                    *valid_filter,
                    Order.service_mode == "DELIVERY",
                    Order.address_neighborhood.is_not(None),
                    func.trim(
                        Order.address_neighborhood
                    )
                    != "",
                )
                .group_by(
                    Order.address_neighborhood,
                )
                .order_by(
                    func.count(Order.id).desc(),
                    func.sum(Order.total).desc(),
                )
                .limit(10)
            ).all()
        ]

        time_distribution = self._time_distribution(
            db,
            valid_filter=valid_filter,
            store_timezone=store_timezone,
        )

        return {
            "store_id": str(store_id),
            "period_hours": hours,
            "timezone": str(
                store_timezone
            ),
            "generated_at": now,
            "summary": {
                "orders_total": int(total_orders),
                "orders_valid": valid_orders,
                "orders_cancelled": int(
                    cancelled_orders
                ),
                "revenue": float(revenue),
                "average_ticket": (
                    round(
                        float(
                            revenue / valid_orders
                        ),
                        2,
                    )
                    if valid_orders
                    else 0.0
                ),
                "unique_customers": unique_customers,
                "new_customers": (
                    customer_segments["new"]
                ),
                "returning_customers": (
                    customer_segments["returning"]
                ),
            },
            "service_modes": service_modes,
            "payment_methods": payment_methods,
            "top_products": top_products,
            "top_modifiers": top_modifiers,
            "top_neighborhoods": top_neighborhoods,
            "orders_by_weekday": (
                time_distribution["weekdays"]
            ),
            "orders_by_hour": (
                time_distribution["hours"]
            ),
        }

    def _customer_segments(
        self,
        db: Session,
        *,
        store_id: UUID,
        since: datetime,
        valid_filter: tuple,
    ) -> dict[str, int]:
        active_customers = (
            select(
                Order.customer_id.label(
                    "customer_id",
                ),
            )
            .where(
                *valid_filter,
            )
            .distinct()
            .subquery()
        )

        active_count = db.scalar(
            select(
                func.count(),
            ).select_from(
                active_customers,
            )
        ) or 0

        if not active_count:
            return {
                "new": 0,
                "returning": 0,
            }

        first_orders = (
            select(
                Order.customer_id.label(
                    "customer_id",
                ),
                func.min(
                    Order.created_at,
                ).label(
                    "first_order_at",
                ),
            )
            .where(
                Order.store_id == store_id,
                Order.status != "CANCELLED",
            )
            .group_by(
                Order.customer_id,
            )
            .subquery()
        )

        new_customers = db.scalar(
            select(
                func.count(),
            )
            .select_from(
                active_customers,
            )
            .join(
                first_orders,
                first_orders.c.customer_id
                == active_customers.c.customer_id,
            )
            .where(
                first_orders.c.first_order_at
                >= since,
            )
        ) or 0

        return {
            "new": int(new_customers),
            "returning": (
                int(active_count)
                - int(new_customers)
            ),
        }

    def _time_distribution(
        self,
        db: Session,
        *,
        valid_filter: tuple,
        store_timezone: ZoneInfo,
    ) -> dict:
        weekday_data = {
            weekday: {
                "orders": 0,
                "revenue": Decimal("0"),
            }
            for weekday in range(7)
        }

        hour_data = {
            hour: {
                "orders": 0,
                "revenue": Decimal("0"),
            }
            for hour in range(24)
        }

        rows = db.execute(
            select(
                Order.created_at,
                Order.total,
            ).where(
                *valid_filter,
            )
        ).all()

        for created_at, total in rows:
            local_datetime = self._as_utc(
                created_at,
            ).astimezone(
                store_timezone,
            )

            amount = Decimal(
                total or 0
            )

            weekday = local_datetime.weekday()
            hour = local_datetime.hour

            weekday_data[weekday]["orders"] += 1
            weekday_data[weekday]["revenue"] += amount

            hour_data[hour]["orders"] += 1
            hour_data[hour]["revenue"] += amount

        weekdays = [
            {
                "weekday": weekday,
                "label": self.WEEKDAY_LABELS[
                    weekday
                ],
                "orders": data["orders"],
                "revenue": float(
                    data["revenue"]
                ),
            }
            for weekday, data in weekday_data.items()
        ]

        hours = [
            {
                "hour": hour,
                "orders": data["orders"],
                "revenue": float(
                    data["revenue"]
                ),
            }
            for hour, data in hour_data.items()
        ]

        return {
            "weekdays": weekdays,
            "hours": hours,
        }

    @staticmethod
    def _timezone(
        timezone_name: str,
    ) -> ZoneInfo:
        try:
            return ZoneInfo(
                timezone_name,
            )
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    @staticmethod
    def _as_utc(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )
