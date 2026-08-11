from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.catalog import Store
from app.services.catalog.prodcon_importer import ConsumerProdconImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa complementos e vínculos do arquivo .prodcon do Consumer."
    )
    parser.add_argument("--file", required=True, help="Caminho do arquivo .prodcon")
    parser.add_argument(
        "--store-slug",
        default="old-burguer-87",
        help="Slug da loja no SmartFoodIA",
    )
    parser.add_argument(
        "--report",
        default="data/reports/consumer_prodcon_import.json",
        help="Arquivo JSON de relatório",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_path = Path(args.file)
    report_path = Path(args.report)

    with SessionLocal() as db:
        store = db.scalar(select(Store).where(Store.slug == args.store_slug))
        if store is None:
            raise SystemExit(f"Loja não encontrada: {args.store_slug}")

        report = ConsumerProdconImportService().import_file(
            db,
            store_id=store.id,
            file_path=file_path,
            report_path=report_path,
        )

    print("Importação .prodcon concluída.")
    print(f"Versão Consumer: {report.consumer_version}")
    print(f"Produtos no arquivo: {report.products_in_file}")
    print(f"Detalhes de produtos: {report.product_details_in_file}")
    print(f"Complementos no arquivo: {report.complement_products_in_file}")
    print(f"Vínculos no arquivo: {report.compatibility_links_in_file}")
    print(f"Complementos criados: {report.modifiers_created}")
    print(f"Complementos atualizados: {report.modifiers_updated}")
    print(f"Grupos criados: {report.groups_created}")
    print(f"Produtos com complementos: {report.products_with_complements}")
    print(f"Vínculos grupo-item criados: {report.group_items_created}")
    print(f"Produtos locais não encontrados: {report.products_not_found}")
    print(f"Detalhes de complemento não encontrados: {report.complement_details_not_found}")
    print(f"Relatório: {report_path}")


if __name__ == "__main__":
    main()
