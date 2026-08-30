from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.integrations.consumer.mapper import map_order
from app.models.catalog import (
    Company,
    Product,
    ProductComboComponent,
    Store,
)
from app.repositories.order import OrderRepository
from app.schemas.cart import CartItemAdd
from app.schemas.customer import CustomerCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.customer import CustomerService
from tests_support import configure_store_open


def setup_combo_order(*, quantity: int = 1):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Old Burguer 87")
    db.add(company)
    db.flush()

    store = Store(
        company_id=company.id,
        name="Old Burguer 87",
        slug=f"old-combo-{uuid4()}",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )
    db.add(store)
    db.flush()

    configure_store_open(db, store)

    trio = Product(
        store_id=store.id,
        external_code="135",
        name="Trio Old Jr.",
        description="Combo de teste",
        price=Decimal("25.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add(trio)
    db.flush()

    components = [
        ProductComboComponent(
            combo_product_id=trio.id,
            component_external_code="122",
            component_name="Batata Frita - Porção",
            quantity=1,
            unit_price=Decimal("9.00"),
            display_order=1,
        ),
        ProductComboComponent(
            combo_product_id=trio.id,
            component_external_code="114",
            component_name="Old Jr.",
            quantity=1,
            unit_price=Decimal("11.00"),
            display_order=2,
        ),
        ProductComboComponent(
            combo_product_id=trio.id,
            component_external_code="66",
            component_name="Bebida",
            quantity=1,
            unit_price=Decimal("5.00"),
            display_order=3,
        ),
    ]

    db.add_all(components)
    db.commit()

    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente Combo",
            phone="97999999999",
        ),
    )

    cart_service = CartService()

    cart = cart_service.create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="TAKEOUT",
    )

    cart = cart_service.add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(
            product_external_code="135",
            quantity=quantity,
        ),
    )

    result = CheckoutService().checkout(
        db,
        cart_id=cart.id,
        payload=CheckoutRequest(
            payment_method="CASH",
        ),
    )

    persisted = OrderRepository().get_by_cart(db, cart.id)

    assert persisted is not None

    return db, result, persisted


def test_checkout_snapshots_combo_without_changing_smartfoodia_price():
    db, result, order = setup_combo_order(quantity=1)

    try:
        # --------------------------------------------------
        # SMARTFOODIA
        # --------------------------------------------------

        assert result.subtotal == Decimal("25.00")
        assert result.total == Decimal("25.00")

        assert order.subtotal == Decimal("25.00")
        assert order.total == Decimal("25.00")

        assert len(order.items) == 1

        item = order.items[0]

        assert item.product_external_code == "135"
        assert item.product_name == "Trio Old Jr."
        assert item.quantity == 1

        # Preço comercial permanece intacto no SmartFoodIA.
        assert item.unit_price == Decimal("25.00")
        assert item.total_price == Decimal("25.00")

        # Os componentes técnicos NÃO viraram modifiers.
        assert item.modifiers == []

        # --------------------------------------------------
        # SNAPSHOT DO COMBO
        # --------------------------------------------------

        assert len(item.combo_components) == 3

        assert [
            component.component_external_code
            for component in item.combo_components
        ] == [
            "122",
            "114",
            "66",
        ]

        assert [
            component.unit_price
            for component in item.combo_components
        ] == [
            Decimal("9.00"),
            Decimal("11.00"),
            Decimal("5.00"),
        ]

        assert sum(
            component.total_price
            for component in item.combo_components
        ) == Decimal("25.00")

        # --------------------------------------------------
        # PAYLOAD CONSUMER
        # --------------------------------------------------

        integration = SimpleNamespace(
            merchant_external_id="test-merchant",
            merchant_name="Old Burguer 87",
        )

        payload = map_order(order, integration)

        consumer_item = payload["item"]["items"][0]

        assert consumer_item["externalCode"] == "135"

        assert consumer_item["unitPrice"] == 0.0
        assert consumer_item["price"] == 0.0

        assert consumer_item["optionsPrice"] == 25.0
        assert consumer_item["totalPrice"] == 25.0

        assert [
            option["externalCode"]
            for option in consumer_item["options"]
        ] == [
            "122",
            "114",
            "66",
        ]

        assert [
            option["unitPrice"]
            for option in consumer_item["options"]
        ] == [
            9.0,
            11.0,
            5.0,
        ]

        assert sum(
            option["price"]
            for option in consumer_item["options"]
        ) == 25.0

    finally:
        db.close()


def test_two_combos_keep_correct_smartfoodia_total_and_snapshot():
    db, result, order = setup_combo_order(quantity=2)

    try:
        # Aqui testamos somente a regra interna.
        # Ainda não assumimos como o Consumer interpreta options
        # quando o item-pai possui quantity > 1.

        assert result.subtotal == Decimal("50.00")
        assert result.total == Decimal("50.00")

        item = order.items[0]

        assert item.quantity == 2
        assert item.unit_price == Decimal("25.00")
        assert item.total_price == Decimal("50.00")

        # A composição é por unidade do combo.
        assert len(item.combo_components) == 3

        assert sum(
            component.total_price
            for component in item.combo_components
        ) == Decimal("25.00")

    finally:
        db.close()


def test_two_combos_are_expanded_for_consumer_as_two_unit_lines():
    db, result, order = setup_combo_order(quantity=2)

    try:
        assert result.subtotal == Decimal("50.00")
        assert result.total == Decimal("50.00")

        integration = SimpleNamespace(
            merchant_external_id="test-merchant",
            merchant_name="Old Burguer 87",
        )

        payload = map_order(order, integration)
        consumer_items = payload["item"]["items"]

        assert len(consumer_items) == 2

        assert [item["quantity"] for item in consumer_items] == [1, 1]
        assert [item["externalCode"] for item in consumer_items] == [
            "135",
            "135",
        ]

        assert [item["unitPrice"] for item in consumer_items] == [
            0.0,
            0.0,
        ]

        assert [item["price"] for item in consumer_items] == [
            0.0,
            0.0,
        ]

        assert [item["optionsPrice"] for item in consumer_items] == [
            25.0,
            25.0,
        ]

        assert [item["totalPrice"] for item in consumer_items] == [
            25.0,
            25.0,
        ]

        assert sum(
            item["totalPrice"]
            for item in consumer_items
        ) == 50.0

        for consumer_item in consumer_items:
            assert [
                option["externalCode"]
                for option in consumer_item["options"]
            ] == [
                "122",
                "114",
                "66",
            ]

            assert sum(
                option["price"]
                for option in consumer_item["options"]
            ) == 25.0

        assert (
            consumer_items[0]["id"]
            != consumer_items[1]["id"]
        )

    finally:
        db.close()


def test_repository_eager_loads_combo_for_detached_consumer_mapping():
    db, result, order = setup_combo_order(quantity=1)

    try:
        order_id = order.id

        # Remove todas as instâncias atuais da sessão para obrigar
        # uma nova consulta pelo repository.
        db.expunge_all()

        reloaded = OrderRepository().get(db, order_id)

        assert reloaded is not None
        assert len(reloaded.items) == 1
        assert len(reloaded.items[0].combo_components) == 3

        # Desanexa novamente. A partir daqui o mapper não poderá
        # buscar nada por lazy-load no banco.
        db.expunge_all()

        integration = SimpleNamespace(
            merchant_external_id="test-merchant",
            merchant_name="Old Burguer 87",
        )

        payload = map_order(reloaded, integration)

        consumer_item = payload["item"]["items"][0]

        assert consumer_item["externalCode"] == "135"
        assert consumer_item["unitPrice"] == 0.0
        assert consumer_item["price"] == 0.0
        assert consumer_item["optionsPrice"] == 25.0
        assert consumer_item["totalPrice"] == 25.0

        assert [
            option["externalCode"]
            for option in consumer_item["options"]
        ] == ["122", "114", "66"]

    finally:
        db.close()
