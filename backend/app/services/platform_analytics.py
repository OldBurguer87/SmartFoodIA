from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Company, Store
from app.models.order import (
    Order,
    OrderItem,
    OrderItemModifier,
)


class PlatformAnalyticsService:
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
        hours: int = 24,
    ) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)

        period_filter = (
            Order.created_at >= since,
        )

        valid_filter = (
            *period_filter,
            Order.status != "CANCELLED",
        )

        companies_total = db.scalar(
            select(func.count(Company.id))
        ) or 0

        companies_active = db.scalar(
            select(func.count(Company.id)).where(
                Company.active.is_(True),
            )
        ) or 0

        stores_total = db.scalar(
            select(func.count(Store.id))
        ) or 0

        stores_active = db.scalar(
            select(func.count(Store.id)).where(
                Store.active.is_(True),
            )
        ) or 0

        orders_total = db.scalar(
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
                func.coalesce(
                    func.sum(Order.total),
                    0,
                ),
                func.count(
                    func.distinct(Order.store_id),
                ),
            ).where(
                *valid_filter,
            )
        ).one()

        valid_orders = int(valid_row[0] or 0)
        revenue = Decimal(valid_row[1] or 0)
        stores_with_orders = int(valid_row[2] or 0)

        companies_with_orders = db.scalar(
            select(
                func.count(
                    func.distinct(Store.company_id),
                )
            )
            .select_from(Order)
            .join(
                Store,
                Store.id == Order.store_id,
            )
            .where(
                *valid_filter,
            )
        ) or 0

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

        states = [
            {
                "state": state,
                "stores": int(stores),
                "orders": int(orders),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for (
                state,
                stores,
                orders,
                amount,
            ) in db.execute(
                select(
                    Store.state,
                    func.count(
                        func.distinct(Order.store_id),
                    ),
                    func.count(Order.id),
                    func.coalesce(
                        func.sum(Order.total),
                        0,
                    ),
                )
                .select_from(Order)
                .join(
                    Store,
                    Store.id == Order.store_id,
                )
                .where(
                    *valid_filter,
                )
                .group_by(
                    Store.state,
                )
                .order_by(
                    func.count(Order.id).desc(),
                    func.sum(Order.total).desc(),
                )
            ).all()
        ]

        cities = [
            {
                "state": state,
                "city": city,
                "stores": int(stores),
                "orders": int(orders),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for (
                state,
                city,
                stores,
                orders,
                amount,
            ) in db.execute(
                select(
                    Store.state,
                    Store.city,
                    func.count(
                        func.distinct(Order.store_id),
                    ),
                    func.count(Order.id),
                    func.coalesce(
                        func.sum(Order.total),
                        0,
                    ),
                )
                .select_from(Order)
                .join(
                    Store,
                    Store.id == Order.store_id,
                )
                .where(
                    *valid_filter,
                )
                .group_by(
                    Store.state,
                    Store.city,
                )
                .order_by(
                    func.count(Order.id).desc(),
                    func.sum(Order.total).desc(),
                )
                .limit(50)
            ).all()
        ]

        top_products = [
            {
                "name": name,
                "stores": int(stores),
                "quantity": int(quantity or 0),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for (
                name,
                stores,
                quantity,
                amount,
            ) in db.execute(
                select(
                    OrderItem.product_name,
                    func.count(
                        func.distinct(Order.store_id),
                    ),
                    func.coalesce(
                        func.sum(OrderItem.quantity),
                        0,
                    ),
                    func.coalesce(
                        func.sum(OrderItem.total_price),
                        0,
                    ),
                )
                .select_from(OrderItem)
                .join(
                    Order,
                    Order.id == OrderItem.order_id,
                )
                .where(
                    *valid_filter,
                )
                .group_by(
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
                .limit(20)
            ).all()
        ]

        top_modifiers = [
            {
                "name": name,
                "stores": int(stores),
                "quantity": int(quantity or 0),
                "revenue": float(
                    Decimal(amount or 0)
                ),
            }
            for (
                name,
                stores,
                quantity,
                amount,
            ) in db.execute(
                select(
                    OrderItemModifier.modifier_name,
                    func.count(
                        func.distinct(Order.store_id),
                    ),
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
                .select_from(OrderItemModifier)
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
                .limit(20)
            ).all()
        ]

        time_distribution = self._time_distribution(
            db,
            valid_filter=valid_filter,
        )

        return {
            "scope": "platform",
            "period_hours": hours,
            "generated_at": now,
            "summary": {
                "companies_total": int(
                    companies_total
                ),
                "companies_active": int(
                    companies_active
                ),
                "companies_with_orders": int(
                    companies_with_orders
                ),
                "stores_total": int(
                    stores_total
                ),
                "stores_active": int(
                    stores_active
                ),
                "stores_with_orders": (
                    stores_with_orders
                ),
                "orders_total": int(
                    orders_total
                ),
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
            },
            "service_modes": service_modes,
            "payment_methods": payment_methods,
            "states": states,
            "cities": cities,
            "top_products": top_products,
            "top_modifiers": top_modifiers,
            "orders_by_weekday": (
                time_distribution["weekdays"]
            ),
            "orders_by_hour": (
                time_distribution["hours"]
            ),
        }

    def _time_distribution(
        self,
        db: Session,
        *,
        valid_filter: tuple,
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
                Store.timezone,
            )
            .select_from(Order)
            .join(
                Store,
                Store.id == Order.store_id,
            )
            .where(
                *valid_filter,
            )
        ).all()

        for created_at, total, timezone_name in rows:
            local_datetime = self._as_utc(
                created_at,
            ).astimezone(
                self._timezone(
                    timezone_name,
                )
            )

            amount = Decimal(total or 0)
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
            return ZoneInfo(timezone_name)
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
