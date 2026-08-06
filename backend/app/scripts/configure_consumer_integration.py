from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.catalog import Store
from app.models.integration import StoreIntegration
from app.services.consumer_partner import hash_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configura a integração Consumer de uma loja."
    )
    parser.add_argument("--store-slug", required=True)
    parser.add_argument("--merchant-id", required=True)
    parser.add_argument("--merchant-name", required=True)
    parser.add_argument(
        "--token",
        default=None,
        help="Não recomendado em produção; omita para digitar de forma segura.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = args.token or getpass.getpass("Token Consumer da loja: ")
    if len(token) < 24:
        raise ValueError("Use um token aleatório com pelo menos 24 caracteres.")

    with SessionLocal() as db:
        store = db.scalar(select(Store).where(Store.slug == args.store_slug))
        if store is None:
            raise ValueError(f"Loja não encontrada: {args.store_slug}")

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

    print("Integração Consumer configurada com sucesso.")
    print("O token não foi salvo em texto puro.")


if __name__ == "__main__":
    main()
