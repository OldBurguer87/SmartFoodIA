from decimal import Decimal
from uuid import uuid4

import pytest
from app.api import customer_operations as customer_operations_api
from app.models.cart import Cart
from app.models.order import Order
from app.models.payment import PaymentReceipt
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


def test_cart_with_items_keeps_original_service_mode() -> None:
    db, store = make_db()
    add_product_with_modifiers(db, store)

    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente",
            phone="97955554444",
        ),
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
        payload=CartItemAdd(
            product_external_code="235",
        ),
    )

    reopened = service.create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="DELIVERY",
    )

    assert reopened.id == cart.id
    assert reopened.service_mode == "TAKEOUT"
    assert len(reopened.items) == 1

@pytest.mark.parametrize(
    "receipt_status",
    ["HUMAN_CONFIRMED", "AUTO_CONFIRMED"],
)
def test_customer_detail_marks_confirmed_pix(
    receipt_status: str,
) -> None:
    db, store = make_db()
    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente PIX",
            phone="97911112222",
        ),
    )

    def make_order(
        display_id: str,
        payment_method: str,
    ) -> Order:
        cart = Cart(
            store_id=store.id,
            customer_id=customer.id,
            status="CHECKED_OUT",
            service_mode="DELIVERY",
        )
        db.add(cart)
        db.flush()
        order = Order(
            store_id=store.id,
            customer_id=customer.id,
            cart_id=cart.id,
            display_id=display_id,
            status="READY_FOR_INTEGRATION",
            service_mode="DELIVERY",
            payment_method=payment_method,
            payment_type=(
                "PREPAID"
                if payment_method == "PIX"
                else "POSTPAID"
            ),
            subtotal=Decimal("30.00"),
            delivery_fee=Decimal("5.00"),
            discount=Decimal("0.00"),
            total=Decimal("35.00"),
            customer_name=customer.name,
            customer_phone=customer.phone,
        )
        db.add(order)
        db.flush()
        return order

    confirmed_pix = make_order("000951", "PIX")
    pending_pix = make_order("000952", "PIX")
    credit_order = make_order("000953", "CREDIT")

    db.add(
        PaymentReceipt(
            store_id=store.id,
            order_id=confirmed_pix.id,
            media_type="DOCUMENT",
            file_sha256="b" * 64,
            status=receipt_status,
        )
    )
    db.commit()

    detail = customer_operations_api.get_customer(
        store_id=store.id,
        customer_id=customer.id,
        db=db,
        _access=None,
    )
    orders = {
        order["display_id"]: order
        for order in detail["orders"]
    }

    assert orders["000951"]["pix_confirmed"] is True
    assert orders["000952"]["pix_confirmed"] is False
    assert orders["000953"]["pix_confirmed"] is False
