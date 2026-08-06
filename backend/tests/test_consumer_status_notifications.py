from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.integrations.notifications import WhatsAppOrderStatusNotifier
from app.models.catalog import Company, Product, Store
from app.models.channel import ChannelAccount, OutboundChannelMessage
from app.models.integration import StoreIntegration
from app.schemas.cart import CartItemAdd
from app.schemas.customer import AddressCreate, CustomerCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.consumer_partner import ConsumerPartnerService
from app.services.customer import CustomerService


class Payload:
    def __init__(self, order_id, status):
        self.orderId = order_id
        self.status = status
        self.justification = None


def setup_context():
    db = Session(create_engine("sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(db.get_bind())
    company = Company(name="Old")
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
    db.flush()
    db.add(StoreIntegration(
        store_id=store.id,
        provider="CONSUMER",
        token_hash="x" * 64,
        merchant_external_id="m1",
        merchant_name="Old Burguer 87",
        active=True,
    ))
    db.add(ChannelAccount(
        store_id=store.id,
        provider="WHATSAPP_CLOUD",
        external_account_id="phone-1",
        verify_token_hash="hash",
        active=True,
    ))
    product = Product(
        store_id=store.id,
        external_code="235",
        name="Old Monster",
        price=Decimal("60"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add(product)
    db.commit()

    customer = CustomerService().find_or_create(
        db,
        CustomerCreate(
            store_id=store.id,
            name="Cliente",
            phone="5597999999999",
        ),
    )
    address = CustomerService().add_address(
        db,
        customer_id=customer.id,
        payload=AddressCreate(
            street="Rua",
            number="1",
            neighborhood="Centro",
            city="Coari",
            state="AM",
        ),
    )
    cart = CartService().create_or_get_open(
        db,
        store_id=store.id,
        customer_id=customer.id,
        service_mode="DELIVERY",
    )
    CartService().add_item(
        db,
        cart_id=cart.id,
        payload=CartItemAdd(product_external_code="235", quantity=1),
    )
    order = CheckoutService().checkout(
        db,
        cart_id=cart.id,
        payload=CheckoutRequest(
            address_id=address.id,
            payment_method="PIX",
            delivery_fee=Decimal("5"),
        ),
    )
    return db, store, order


def test_consumer_status_queues_whatsapp_notification_once():
    db, store, order = setup_context()
    service = ConsumerPartnerService()

    first = service.update_status(
        db,
        store=store,
        payload=Payload(order.id, "CONFIRMED"),
    )
    second = service.update_status(
        db,
        store=store,
        payload=Payload(order.id, "CONFIRMED"),
    )

    messages = list(db.scalars(select(OutboundChannelMessage)))
    assert "alterado" in first.reasonPhrase
    assert "já estava" in second.reasonPhrase
    assert len(messages) == 1
    assert messages[0].recipient == "5597999999999"
    assert "confirmado" in messages[0].content.lower()


def test_notifier_skips_when_whatsapp_account_is_missing():
    db, store, order = setup_context()
    account = db.scalar(select(ChannelAccount))
    db.delete(account)
    db.commit()

    sent = WhatsAppOrderStatusNotifier().notify_status_change(
        db,
        store_id=store.id,
        order_id=order.id,
        status="DISPATCHED",
    )
    assert sent is False
