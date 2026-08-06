from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from app.channels.whatsapp.security import hash_verify_token
from app.database.session import SessionLocal
from app.models.catalog import Store
from app.models.channel import ChannelAccount


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configura o canal WhatsApp Cloud API.")
    parser.add_argument("--store-slug", required=True)
    parser.add_argument("--phone-number-id", required=True)
    parser.add_argument("--display-phone-number", default=None)
    parser.add_argument("--verify-token", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    verify_token_value = args.verify_token or getpass.getpass("Verify token do webhook: ")
    if len(verify_token_value) < 16:
        raise ValueError("Use um verify token com pelo menos 16 caracteres.")

    with SessionLocal() as db:
        store = db.scalar(select(Store).where(Store.slug == args.store_slug))
        if store is None:
            raise ValueError(f"Loja não encontrada: {args.store_slug}")

        account = db.scalar(
            select(ChannelAccount).where(
                ChannelAccount.provider == "WHATSAPP_CLOUD",
                ChannelAccount.external_account_id == args.phone_number_id,
            )
        )
        if account is None:
            account = ChannelAccount(
                store_id=store.id,
                provider="WHATSAPP_CLOUD",
                external_account_id=args.phone_number_id,
                display_phone_number=args.display_phone_number,
                verify_token_hash=hash_verify_token(verify_token_value),
                active=True,
            )
            db.add(account)
        else:
            account.store_id = store.id
            account.display_phone_number = args.display_phone_number
            account.verify_token_hash = hash_verify_token(verify_token_value)
            account.active = True
        db.commit()

    print("Canal WhatsApp configurado com sucesso.")
    print("O verify token não foi salvo em texto puro.")


if __name__ == "__main__":
    main()
