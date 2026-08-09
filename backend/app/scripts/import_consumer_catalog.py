from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.catalog import Company, Store
from app.services.catalog.importer import ConsumerCatalogImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa a planilha de cardápio exportada pelo Consumer."
    )
    parser.add_argument("--file", required=True, help="Caminho do arquivo .xlsx")
    parser.add_argument(
        "--store-slug",
        default="old-burguer-87",
        help="Slug da loja no SmartFoodIA",
    )
    parser.add_argument(
        "--store-name",
        default="Old Burguer 87",
        help="Nome da loja, usado somente quando ela ainda não existe",
    )
    parser.add_argument(
        "--company-name",
        default="Old Burguer 87",
        help="Nome da empresa, usado somente no primeiro cadastro",
    )
    parser.add_argument(
        "--report",
        default="data/reports/consumer_catalog_import.json",
        help="Arquivo JSON de relatório",
    )
    return parser.parse_args()


def ensure_store(db, *, company_name: str, store_name: str, store_slug: str) -> Store:
    store = db.scalar(select(Store).where(Store.slug == store_slug))
    if store is not None:
        return store

    company = db.scalar(select(Company).where(Company.name == company_name))
    if company is None:
        company = Company(name=company_name, active=True)
        db.add(company)
        db.flush()

    store = Store(
        company_id=company.id,
        name=store_name,
        slug=store_slug,
        city="Coari",
        state="AM",
        timezone="America/Manaus",
        active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def main() -> None:
    args = parse_args()
    file_path = Path(args.file)
    report_path = Path(args.report)

    with SessionLocal() as db:
        store = ensure_store(
            db,
            company_name=args.company_name,
            store_name=args.store_name,
            store_slug=args.store_slug,
        )
        report = ConsumerCatalogImportService().import_workbook(
            db,
            store_id=store.id,
            file_path=file_path,
            report_path=report_path,
        )

    print("Importação concluída.")
    print(f"Linhas lidas: {report.rows_read}")
    print(f"Produtos criados: {report.products_created}")
    print(f"Produtos atualizados: {report.products_updated}")
    print(f"Produtos desativados: {report.products_deactivated}")
    print(f"Conflitos ignorados: {report.conflicts_skipped}")
    print(f"Linhas inválidas: {report.invalid_rows}")
    print(f"Relatório: {report_path}")


if __name__ == "__main__":
    main()
