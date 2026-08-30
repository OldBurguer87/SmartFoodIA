from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.integrations.consumer.mapper import map_order


def integration():
    return SimpleNamespace(
        merchant_external_id="test-merchant",
        merchant_name="Old Burguer 87",
    )


def make_order(
    *,
    item,
    subtotal,
    total,
    payment_method="CASH",
    payment_type="PENDING",
):
    return SimpleNamespace(
        id=uuid4(),
        display_id="TEST001",
        service_mode="TAKEOUT",
        created_at=datetime.now(timezone.utc),
        items=[item],
        subtotal=Decimal(subtotal),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal(total),
        payment_method=payment_method,
        payment_type=payment_type,
        change_for=None,
        customer_id=uuid4(),
        customer_name="Cliente Teste",
        customer_phone="5597999999999",
        address_state=None,
        address_city=None,
        address_street=None,
        address_number=None,
        address_neighborhood=None,
        address_postal_code=None,
        address_complement=None,
        address_reference=None,
    )


def test_combo_is_sent_as_zero_parent_plus_priced_options():
    components = [
        SimpleNamespace(
            id=uuid4(),
            component_external_code="122",
            component_name="Batata Frita - Porção",
            quantity=1,
            unit_price=Decimal("9.00"),
            total_price=Decimal("9.00"),
        ),
        SimpleNamespace(
            id=uuid4(),
            component_external_code="114",
            component_name="Old Jr.",
            quantity=1,
            unit_price=Decimal("11.00"),
            total_price=Decimal("11.00"),
        ),
        SimpleNamespace(
            id=uuid4(),
            component_external_code="66",
            component_name="Bebida",
            quantity=1,
            unit_price=Decimal("5.00"),
            total_price=Decimal("5.00"),
        ),
    ]

    item = SimpleNamespace(
        id=uuid4(),
        product_external_code="135",
        product_name="Trio Old Jr.",
        quantity=1,
        unit_price=Decimal("25.00"),
        total_price=Decimal("25.00"),
        observations=None,
        combo_components=components,
        modifiers=[],
    )

    payload = map_order(
        make_order(
            item=item,
            subtotal="25.00",
            total="25.00",
        ),
        integration(),
    )

    consumer_item = payload["item"]["items"][0]

    assert consumer_item["externalCode"] == "135"

    # O pai técnico do combo não leva preço próprio ao Consumer.
    assert consumer_item["unitPrice"] == 0.0
    assert consumer_item["price"] == 0.0

    # O pedido continua valendo R$ 25.
    assert consumer_item["optionsPrice"] == 25.0
    assert consumer_item["totalPrice"] == 25.0

    options = consumer_item["options"]

    assert [o["externalCode"] for o in options] == [
        "122",
        "114",
        "66",
    ]

    assert [o["unitPrice"] for o in options] == [
        9.0,
        11.0,
        5.0,
    ]

    assert sum(o["price"] for o in options) == 25.0

    assert payload["item"]["total"]["subTotal"] == 25.0
    assert payload["item"]["total"]["orderAmount"] == 25.0


def test_regular_product_keeps_existing_consumer_contract():
    item = SimpleNamespace(
        id=uuid4(),
        product_external_code="200",
        product_name="X Bacon",
        quantity=1,
        unit_price=Decimal("13.00"),
        total_price=Decimal("13.00"),
        observations=None,
        combo_components=[],
        modifiers=[],
    )

    payload = map_order(
        make_order(
            item=item,
            subtotal="13.00",
            total="13.00",
        ),
        integration(),
    )

    consumer_item = payload["item"]["items"][0]

    assert consumer_item["unitPrice"] == 13.0
    assert consumer_item["price"] == 13.0
    assert consumer_item["totalPrice"] == 13.0
    assert consumer_item["optionsPrice"] == 0.0
    assert consumer_item["options"] is None


def test_pix_payment_remains_online_and_prepaid():
    item = SimpleNamespace(
        id=uuid4(),
        product_external_code="200",
        product_name="X Bacon",
        quantity=1,
        unit_price=Decimal("13.00"),
        total_price=Decimal("13.00"),
        observations=None,
        combo_components=[],
        modifiers=[],
    )

    payload = map_order(
        make_order(
            item=item,
            subtotal="13.00",
            total="13.00",
            payment_method="PIX",
            payment_type="PENDING",
        ),
        integration(),
    )

    payments = payload["item"]["payments"]

    assert payments["methods"][0]["method"] == "PIX"
    assert payments["methods"][0]["type"] == "ONLINE"
    assert payments["methods"][0]["prepaid"] is True
    assert payments["pending"] == 0.0
    assert payments["prepaid"] == 13.0
