from __future__ import annotations

from decimal import Decimal
from typing import Any


def _get(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _to_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def extract_openai_usage(
    response: Any,
    *,
    requested_model: str | None = None,
) -> dict[str, Any] | None:
    usage = _get(response, "usage")

    if usage is None:
        return None

    input_details = _get(usage, "input_tokens_details")
    output_details = _get(usage, "output_tokens_details")

    input_tokens = _to_int(_get(usage, "input_tokens"))
    output_tokens = _to_int(_get(usage, "output_tokens"))
    total_tokens = _to_int(_get(usage, "total_tokens"))

    cached_tokens = _to_int(
        _get(input_details, "cached_tokens")
    )

    reasoning_tokens = _to_int(
        _get(output_details, "reasoning_tokens")
    )

    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    model = str(
        _get(response, "model")
        or requested_model
        or ""
    ).strip() or None

    prices = {
        "gpt-5.5": (
            Decimal("5.00"),
            Decimal("0.50"),
            Decimal("30.00"),
        ),
        "gpt-5.4-mini": (
            Decimal("0.75"),
            Decimal("0.075"),
            Decimal("4.50"),
        ),
    }

    price = next(
        (
            rates
            for name, rates in prices.items()
            if model == name
            or str(model).startswith(name + "-")
        ),
        None,
    )

    estimated_cost_usd = None

    if price:
        input_rate, cache_rate, output_rate = price
        uncached = max(0, input_tokens - cached_tokens)

        cost = (
            Decimal(uncached) * input_rate
            + Decimal(cached_tokens) * cache_rate
            + Decimal(output_tokens) * output_rate
        ) / Decimal("1000000")

        estimated_cost_usd = str(
            cost.quantize(Decimal("0.00000001"))
        )

    return {
        "model": model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": max(
            0,
            input_tokens - cached_tokens,
        ),
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }
