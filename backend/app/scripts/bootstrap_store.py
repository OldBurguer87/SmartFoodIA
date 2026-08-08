from __future__ import annotations

import argparse

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.catalog import Company, Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cria ou atualiza uma loja base para o SmartFoodIA."
    )
    parser.add_argument("--store-slug", required=True)
    parser.add_argument("--store-name", required=True)
    parser.add_argument("--company-name", default=None)
    parser.add_argument("--document-number", default=None)
    parser.add_argument("--city", default="Coari")
    parser.add_argument("--state", default="AM")
    parser.add_argument("--timezone", default="America/Manaus")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    company_name = args.company_name or args.store_name

    with SessionLocal() as db:
        store = db.scalar(select(Store).where(Store.slug == args.store_slug))
        if store is not None:
            store.name = args.store_name
            store.city = args.city
            store.state = args.state
            store.timezone = args.timezone
            store.active = True
            db.commit()
            print(f"Loja atualizada: {store.name} ({store.slug})")
            return

        company = None
        if args.document_number:
            company = db.scalar(
                select(Company).where(Company.document_number == args.document_number)
            )
        if company is None:
            company = db.scalar(select(Company).where(Company.name == company_name))
        if company is None:
            company = Company(
                name=company_name,
                document_number=args.document_number,
                active=True,
            )
            db.add(company)
            db.flush()

        store = Store(
            company_id=company.id,
            name=args.store_name,
            slug=args.store_slug,
            city=args.city,
            state=args.state,
            timezone=args.timezone,
            active=True,
        )
        db.add(store)
        db.commit()

    print(f"Loja criada: {args.store_name} ({args.store_slug})")


if __name__ == "__main__":
    main()
