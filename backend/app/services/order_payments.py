from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentPart:
    method: str
    payment_type: str
    amount: Decimal
    change_for: Decimal | None = None
    position: int = 1


def payment_parts_from_order(order) -> list[PaymentPart]:
    persisted = list(
        getattr(order, "payments", None) or []
    )

    if persisted:
        return [
            PaymentPart(
                method=str(payment.method).upper(),
                payment_type=str(payment.payment_type).upper(),
                amount=Decimal(str(payment.amount)),
                change_for=(
                    Decimal(str(payment.change_for))
                    if payment.change_for is not None
                    else None
                ),
                position=int(payment.position),
            )
            for payment in sorted(
                persisted,
                key=lambda item: item.position,
            )
        ]

    return [
        PaymentPart(
            method=str(order.payment_method).upper(),
            payment_type=str(order.payment_type).upper(),
            amount=Decimal(str(order.total)),
            change_for=(
                Decimal(str(order.change_for))
                if order.change_for is not None
                else None
            ),
            position=1,
        )
    ]


def has_payment_method(order, method: str) -> bool:
    wanted = str(method).upper()

    return any(
        payment.method == wanted
        for payment in payment_parts_from_order(order)
    )


def payment_amount(order, method: str) -> Decimal | None:
    wanted = str(method).upper()

    values = [
        payment.amount
        for payment in payment_parts_from_order(order)
        if payment.method == wanted
    ]

    if not values:
        return None

    return sum(values, Decimal("0.00"))
