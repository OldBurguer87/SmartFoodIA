from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models.catalog import (
    Category,
    Company,
    Modifier,
    ModifierGroup,
    ModifierGroupItem,
    Product,
    ProductModifierGroup,
    Store,
)
from app.services.catalog.exceptions import ProductNotFoundError
from app.services.catalog.search import normalize_text, relevance_score
from app.services.catalog.service import CatalogService


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture()
def catalog(db: Session):
    company = Company(name="Old Burguer 87")
    store = Store(company=company, name="Old Burguer 87", slug="old-burguer-87")
    category = Category(store=store, name="Hambúrgueres")
    product = Product(
        store=store,
        category=category,
        external_code="235",
        name="Old Mônster",
        description="Hambúrguer artesanal grande com bacon e queijo",
        price=Decimal("60.00"),
    )
    unavailable = Product(
        store=store,
        category=category,
        external_code="999",
        name="Produto Indisponível",
        description="Somente teste",
        price=Decimal("1.00"),
        available_for_delivery=False,
    )
    group = ModifierGroup(
        store=store,
        name="Adicionais",
        min_select=0,
        max_select=4,
        display_order=1,
    )
    cheese = Modifier(
        store=store,
        external_code="39",
        name="Queijo",
        price=Decimal("3.00"),
    )
    bacon = Modifier(
        store=store,
        external_code="37",
        name="Bacon",
        price=Decimal("5.00"),
    )
    product.modifier_group_links.append(
        ProductModifierGroup(group=group, display_order=1)
    )
    group.modifier_links.extend(
        [
            ModifierGroupItem(modifier=cheese, display_order=1, max_quantity=3),
            ModifierGroupItem(modifier=bacon, display_order=2, max_quantity=2),
        ]
    )
    db.add_all([company, product, unavailable])
    db.commit()
    return store, product


def test_normalize_text_removes_accents_and_punctuation() -> None:
    assert normalize_text("  Old MÔNSTER!!! ") == "old monster"


def test_relevance_exact_name_is_maximum() -> None:
    assert relevance_score(
        "old monster", name="Old Monster", description=None, category=None
    ) == 1.0


def test_find_product_by_partial_name(db: Session, catalog) -> None:
    store, product = catalog
    found = CatalogService().find_best_product(
        db,
        store_id=store.id,
        query="monster",
    )
    assert found.id == product.id
    assert found.name == "Old Mônster"
    assert found.modifier_groups[0].modifiers[0].external_code == "39"


def test_search_uses_description(db: Session, catalog) -> None:
    store, _ = catalog
    results = CatalogService().search_products(
        db,
        store_id=store.id,
        query="artesanal bacon",
    )
    assert results
    assert results[0].product.external_code == "235"


def test_delivery_filter_excludes_unavailable_product(db: Session, catalog) -> None:
    store, _ = catalog
    products = CatalogService().list_available_products(
        db,
        store_id=store.id,
        delivery=True,
    )
    assert {product.external_code for product in products} == {"235"}


def test_unknown_product_raises(db: Session, catalog) -> None:
    store, _ = catalog
    with pytest.raises(ProductNotFoundError):
        CatalogService().find_best_product(
            db,
            store_id=store.id,
            query="sushi de salmao",
        )
