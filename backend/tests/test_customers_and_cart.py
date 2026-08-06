from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import (
    Company,
    Modifier,
    ModifierGroup,
    ModifierGroupItem,
    Product,
    ProductModifierGroup,
    Store,
)
from app.schemas.cart import CartItemAdd, CartItemUpdate, ModifierSelection
from app.schemas.customer import AddressCreate, CustomerCreate
from app.services.cart import CartService, CartValidationError
from app.services.customer import CustomerService


def make_db() -> tuple[Session, Store]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Old Burguer 87")
    db.add(company)
    db.flush()
    store = Store(
        company_id=company.id,
        name="Old Burguer 87",
        slug=f"old-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return db, store


def add_product_with_modifiers(db: Session, store: Store) -> Product:
    product = Product(
        store_id=store.id,
        external_code="235",
        name="Old Monster",
        description="Hambúrguer artesanal",
        price=Decimal("60.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    group = ModifierGroup(
        store_id=store.id,
        name="Adicionais",
        min_select=0,
        max_select=3,
        allow_repeat=True,
        active=True,
    )
    bacon = Modifier(
        store_id=store.id,
        external_code="37",
        name="Bacon",
        price=Decimal("5.00"),
        active=True,
    )
    cheese = Modifier(
        store_id=store.id,
        external_code="39",
        name="Queijo",
        price=Decimal("3.00"),
        active=True,
    )
    db.add_all([product, group, bacon, cheese])
    db.flush()
    db.add(ProductModifierGroup(product_id=product.id, modifier_group_id=group.id))
    db.add_all(
        [
            ModifierGroupItem(
                modifier_group_id=group.id,
                modifier_id=bacon.id,
                min_quantity=0,
                max_quantity=3,
            ),
            ModifierGroupItem(
                modifier_group_id=group.id,
                modifier_id=cheese.id,
                min_quantity=0,
                max_quantity=3,
            ),
        ]
    )
    db.commit()
    return product


def test_customer_is_found_by_normalized_phone() -> None:
    db, store = make_db()
    service = CustomerService()

    first = service.find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="João",
            phone="(97) 99999-9999",
        ),
    )
    second = service.find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="João da Silva",
            phone="97999999999",
        ),
    )

    assert first.id == second.id
    assert second.name == "João da Silva"
    assert second.phone == "97999999999"


def test_first_address_becomes_default() -> None:
    db, store = make_db()
    service = CustomerService()
    customer = service.find_or_create(
        db,
        CustomerCreate(store_id=store.id, name="Maria", phone="97988887777"),
    )

    address = service.add_address(
        db,
        customer_id=customer.id,
        payload=AddressCreate(
            street="Rua Principal",
            number="10",
            neighborhood="Centro",
        ),
    )

    assert address.is_default is True


def test_cart_calculates_product_and_modifiers() -> None:
    db, store = make_db()
    add_product_with_modifiers(db, store)
    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(store_id=store.id, name="Cliente", phone="97977776666"),
    )
    service = CartService()
    cart = service.create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="DELIVERY",
    )

    updated = service.add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(
            product_external_code="235",
            quantity=2,
            observations="Sem cebola",
            modifiers=[
                ModifierSelection(external_code="37", quantity=1),
                ModifierSelection(external_code="39", quantity=2),
            ],
        ),
    )

    assert updated.subtotal == Decimal("142.00")
    assert updated.items[0].total == Decimal("142.00")
    assert updated.items[0].observations == "Sem cebola"


def test_cart_rejects_incompatible_modifier() -> None:
    db, store = make_db()
    add_product_with_modifiers(db, store)
    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(store_id=store.id, name="Cliente", phone="97977775555"),
    )
    service = CartService()
    cart = service.create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="DELIVERY",
    )

    with pytest.raises(CartValidationError, match="incompatíveis"):
        service.add_item(
            db,
            cart_id=cart.id,
            payload=CartItemAdd(
                product_external_code="235",
                modifiers=[ModifierSelection(external_code="999")],
            ),
        )


def test_cart_updates_and_removes_item() -> None:
    db, store = make_db()
    add_product_with_modifiers(db, store)
    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(store_id=store.id, name="Cliente", phone="97966665555"),
    )
    service = CartService()
    cart = service.create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="TAKEOUT",
    )
    cart = service.add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(product_external_code="235"),
    )
    item_id = cart.items[0].id

    cart = service.update_item(
        db,
        cart_id=cart.id,
        item_id=item_id,
        payload=CartItemUpdate(quantity=3, observations="Bem passado"),
    )
    assert cart.subtotal == Decimal("180.00")

    cart = service.remove_item(db, cart_id=cart.id, item_id=item_id)
    assert cart.items == []
    assert cart.subtotal == Decimal("0.00")
