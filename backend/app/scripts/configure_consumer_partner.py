from __future__ import annotations

import argparse
import secrets

from sqlalchemy import select

from app.database.session import SessionLocal
from app.integrations.consumer.auth import hash_token
from app.models.catalog import Store
from app.models.integration import StoreIntegration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configura a integração Consumer Partner para uma loja."
    )
    parser.add_argument("--store-slug", required=True)
    parser.add_argument("--merchant-id", required=True)
    parser.add_argument("--merchant-name", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    token = args.token or secrets.token_urlsafe(32)
    base_url = args.base_url.rstrip("/")

    with SessionLocal() as db:
        store = db.scalar(select(Store).where(Store.slug == args.store_slug))
        if store is None:
            raise SystemExit(f"Loja não encontrada: {args.store_slug}")

        integration = db.scalar(
            select(StoreIntegration).where(
                StoreIntegration.store_id == store.id,
                StoreIntegration.provider == "CONSUMER",
            )
        )
        if integration is None:
            integration = StoreIntegration(
                store_id=store.id,
                provider="CONSUMER",
                token_hash=hash_token(token),
                merchant_external_id=args.merchant_id,
                merchant_name=args.merchant_name,
                active=True,
            )
            db.add(integration)
        else:
            integration.token_hash = hash_token(token)
            integration.merchant_external_id = args.merchant_id
            integration.merchant_name = args.merchant_name
            integration.active = True
        db.commit()

    prefix = f"{base_url}/api/v1/integrations/consumer/{args.store_slug}"
    print("Integração Consumer configurada com sucesso.")
    print(f"TOKEN={token}")
    print(f"POLLING_URL={prefix}/events")
    print(f"ORDER_DETAILS_URL={prefix}/orders/{{order_id}}")
    print(f"ORDER_EVENT_URL={prefix}/orders/{{order_id}}/events")
    print(f"ORDER_STATUS_URL={prefix}/orders/{{order_id}}/status")
    print("Guarde o token em local seguro. Ele não poderá ser recuperado do banco.")


if __name__ == "__main__":
    main()
