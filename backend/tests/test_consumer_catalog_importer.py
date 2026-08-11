from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Category, Company, Product, Store
from app.services.catalog.importer import ConsumerCatalogImportService


HEADERS = (
    "...",
    "Categoria (iFood)",
    "Categoria (Consumer)",
    "Código PDV",
    "Produto",
    "Preço",
    "Descrição",
)


def make_database() -> tuple[Session, Store]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Old Burguer 87")
    db.add(company)
    db.flush()
    store = Store(
        company_id=company.id,
        name="Old Burguer 87",
        slug=f"old-burguer-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return db, store


def create_workbook(path: Path, rows: list[tuple]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_import_creates_categories_and_products(tmp_path: Path) -> None:
    file_path = tmp_path / "catalog.xlsx"
    create_workbook(
        file_path,
        [
            (True, "Modelo", "Gourmet", "235", "Old Monster", 60, "Descrição"),
            (True, "Modelo", "Bebidas", "90", "Coca-Cola 2L", 12, ""),
        ],
    )
    db, store = make_database()

    report = ConsumerCatalogImportService().import_workbook(
        db,
        store_id=store.id,
        file_path=file_path,
    )

    assert report.products_created == 2
    assert report.categories_created == 2
    assert db.scalar(select(Product).where(Product.external_code == "235")).price == Decimal(
        "60.00"
    )


def test_import_is_idempotent_and_updates_changed_product(tmp_path: Path) -> None:
    file_path = tmp_path / "catalog.xlsx"
    create_workbook(
        file_path,
        [(True, "Modelo", "Gourmet", "235", "Old Monster", 60, "Descrição")],
    )
    db, store = make_database()
    service = ConsumerCatalogImportService()

    first = service.import_workbook(db, store_id=store.id, file_path=file_path)
    assert first.products_created == 1

    create_workbook(
        file_path,
        [(True, "Modelo", "Gourmet", "235", "Old Monster", 62, "Nova descrição")],
    )
    second = service.import_workbook(db, store_id=store.id, file_path=file_path)

    assert second.products_created == 0
    assert second.products_updated == 1
    product = db.scalar(select(Product).where(Product.external_code == "235"))
    assert product.price == Decimal("62.00")
    assert product.description == "Nova descrição"


def test_regular_product_wins_over_combo_variant(tmp_path: Path) -> None:
    file_path = tmp_path / "catalog.xlsx"
    create_workbook(
        file_path,
        [
            (True, "Modelo Padrão", "Bebidas", "59", "Suco de Acerola", 7, ""),
            (True, "Modelo Padrão (Combo)", "Bebidas", "59", "Suco de Acerola", 5, ""),
        ],
    )
    db, store = make_database()

    report = ConsumerCatalogImportService().import_workbook(
        db,
        store_id=store.id,
        file_path=file_path,
    )

    product = db.scalar(select(Product).where(Product.external_code == "59"))
    assert report.conflicts_skipped == 0
    assert report.duplicates_ignored == 1
    assert product is not None
    assert product.price == Decimal("7.00")


def test_conflict_between_regular_rows_is_still_blocked(tmp_path: Path) -> None:
    file_path = tmp_path / "catalog.xlsx"
    create_workbook(
        file_path,
        [
            (True, "Modelo Padrão", "Bebidas", "59", "Suco de Acerola", 7, ""),
            (True, "Modelo Alternativo", "Bebidas", "59", "Suco de Acerola", 5, ""),
        ],
    )
    db, store = make_database()

    report = ConsumerCatalogImportService().import_workbook(
        db,
        store_id=store.id,
        file_path=file_path,
    )

    assert report.conflicts_skipped == 1
    assert db.scalar(select(Product).where(Product.external_code == "59")) is None


def test_equal_duplicates_are_deduplicated(tmp_path: Path) -> None:
    file_path = tmp_path / "catalog.xlsx"
    duplicate = (True, "Modelo", "Gourmet", "255", "Old Fritas", 20, "Descrição")
    create_workbook(file_path, [duplicate, duplicate])
    db, store = make_database()

    report = ConsumerCatalogImportService().import_workbook(
        db,
        store_id=store.id,
        file_path=file_path,
    )

    assert report.products_created == 1
    assert report.duplicates_ignored == 1
