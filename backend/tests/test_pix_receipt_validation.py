from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import app.models  # noqa: F401

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.commercial import StoreCommercialRules
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.services.pix_receipt_validation import (
    PixReceiptValidationService,
)


class FakeAnalyzer:
    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id

    def analyze(self, *, receipt):
        now_local = datetime.now(
            ZoneInfo("America/Manaus")
        )

        return {
            "is_pix_receipt": True,
            "receiver_name": "Old Burguer 87",
            "receiver_document": "12345678901",
            "pix_key": "pix@oldburguer.test",
            "amount": 7.00,
            "paid_date": now_local.strftime("%Y-%m-%d"),
            "paid_time": now_local.strftime("%H:%M:%S"),
            "transaction_id": self.transaction_id,
            "transaction_status": "CONCLUIDO",
            "payment_completed": True,
            "payer_name": "Cliente Teste",
            "institution": None,
            "confidence": 0.99,
            "notes": None,
        }


def test_changed_file_with_same_transaction_id_requires_review():
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
    db.flush()

    rules = StoreCommercialRules(
        store_id=store.id,
        pix_receiver_name="Old Burguer 87",
        pix_receiver_document="12345678901",
        pix_key="pix@oldburguer.test",
        pix_auto_verify_enabled=True,
        pix_receipt_max_age_minutes=360,
        pix_amount_tolerance=Decimal("0.01"),
    )
    db.add(rules)

    previous_order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000001",
        status="PLACED",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("7.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("7.00"),
        customer_name="Cliente Anterior",
        customer_phone="5597999990001",
    )

    current_order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="000002",
        status="PLACED",
        service_mode="TAKEOUT",
        payment_method="PIX",
        payment_type="ONLINE",
        subtotal=Decimal("7.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("7.00"),
        customer_name="Cliente Atual",
        customer_phone="5597999990002",
    )

    db.add_all([previous_order, current_order])
    db.flush()

    transaction_id = "E2E-REUTILIZADO-123"

    previous = PaymentReceipt(
        store_id=store.id,
        order_id=previous_order.id,
        external_media_id="media-original",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256="a" * 64,
        status="AUTO_CONFIRMED",
        extracted_transaction_id=transaction_id,
    )

    current = PaymentReceipt(
        store_id=store.id,
        order_id=current_order.id,
        external_media_id="media-modificada",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256="b" * 64,
        status="RECEIVED",
        validation_json={
            "candidate_orders": ["000002"],
        },
    )

    db.add_all([previous, current])
    db.commit()
    db.refresh(current)

    result = PixReceiptValidationService(
        analyzer=FakeAnalyzer(transaction_id)
    ).process(
        db,
        receipt=current,
    )

    assert previous.file_sha256 != current.file_sha256

    assert result.status == "NEEDS_REVIEW"

    assert (
        result.validation_json["checks"][
            "duplicate_transaction_id"
        ]
        is True
    )

    assert (
        "DUPLICATE_TRANSACTION_ID"
        in result.validation_json["reasons"]
    )

    assert result.validation_json["decision"] == "NEEDS_REVIEW"
