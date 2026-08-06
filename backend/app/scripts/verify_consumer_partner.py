from __future__ import annotations

import argparse
import json
import sys
from uuid import uuid4

import httpx


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "Valida a exposição pública e o contrato básico da API Parceiro "
            "Consumer sem modificar pedidos."
        )
    )
    value.add_argument("--store-slug", required=True)
    value.add_argument("--base-url", required=True)
    value.add_argument("--token", required=True)
    value.add_argument("--timeout", type=float, default=20.0)
    return value


def main() -> None:
    args = parser().parse_args()
    base_url = args.base_url.rstrip("/")
    if not base_url.startswith("https://"):
        raise SystemExit("A homologação exige uma URL pública HTTPS.")

    prefix = f"{base_url}/api/v1/integrations/consumer/{args.store_slug}"
    headers = {"Authorization": f"Bearer {args.token}"}
    failures: list[str] = []

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        diagnostics = client.get(
            f"{prefix}/diagnostics",
            params={"base_url": base_url},
            headers=headers,
        )
        check_status(
            diagnostics,
            expected=200,
            label="diagnostics",
            failures=failures,
        )

        polling = client.get(f"{prefix}/events", headers=headers)
        check_status(
            polling,
            expected=200,
            label="polling",
            failures=failures,
        )
        if polling.status_code == 200:
            body = polling.json()
            required = {"items", "statusCode", "reasonPhrase"}
            missing = required.difference(body)
            if missing:
                failures.append(
                    "polling: campos ausentes: " + ", ".join(sorted(missing))
                )
            elif body.get("statusCode") != 0:
                failures.append("polling: statusCode diferente de 0")

        unauthenticated = client.get(f"{prefix}/events")
        check_status(
            unauthenticated,
            expected=401,
            label="authentication_missing",
            failures=failures,
        )

        invalid_token = client.get(
            f"{prefix}/events",
            headers={"Authorization": "Bearer token-invalido-homologacao"},
        )
        check_status(
            invalid_token,
            expected=401,
            label="authentication_invalid",
            failures=failures,
        )

        unknown_order = client.get(
            f"{prefix}/orders/{uuid4()}",
            headers=headers,
        )
        check_status(
            unknown_order,
            expected=404,
            label="unknown_order",
            failures=failures,
        )

    result = {
        "base_url": base_url,
        "store_slug": args.store_slug,
        "success": not failures,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if failures:
        raise SystemExit(1)


def check_status(
    response: httpx.Response,
    *,
    expected: int,
    label: str,
    failures: list[str],
) -> None:
    if response.status_code != expected:
        body = response.text[:500]
        failures.append(
            f"{label}: esperado HTTP {expected}, recebido "
            f"{response.status_code}. Corpo: {body}"
        )


if __name__ == "__main__":
    main()
