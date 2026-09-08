import base64
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import app.models  # noqa: F401

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.commercial import StoreCommercialRules
from app.models.order import Order, OrderPayment
from app.models.payment import PaymentReceipt
from app.services.pix_receipt_validation import (
    PixReceiptAnalyzer,
    PixReceiptValidationService,
)


class FakeAnalyzer:
    def __init__(self, transaction_id: str, amount=7.00):
        self.transaction_id = transaction_id
        self.amount = amount

    def analyze(self, *, receipt):
        now_local = datetime.now(
            ZoneInfo("America/Manaus")
        )

        return {
            "is_pix_receipt": True,
            "receiver_name": "Old Burguer 87",
            "receiver_document": "12345678901",
            "pix_key": "pix@oldburguer.test",
            "amount": self.amount,
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



class FakeOpenAIUsage:
    def model_dump(self):
        return {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        }


class FakeOpenAIResponses:
    def __init__(self):
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs

        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "is_pix_receipt": True,
                    "receiver_name": "Old Burguer 87",
                    "receiver_document": None,
                    "pix_key": None,
                    "amount": 50.00,
                    "paid_date": "2026-08-20",
                    "paid_time": "20:30:00",
                    "transaction_id": "TESTE-E2E",
                    "transaction_status": "CONCLUIDO",
                    "payment_completed": True,
                    "payer_name": "Cliente Teste",
                    "institution": "MERCADO PAGO IP LTDA.",
                    "confidence": 0.99,
                    "notes": None,
                }
            ),
            usage=FakeOpenAIUsage(),
        )


class FakeOpenAIClient:
    def __init__(self):
        self.responses = FakeOpenAIResponses()


def test_pix_analyzer_returns_usage_tuple_for_image(tmp_path):
    image = tmp_path / "comprovante.jpg"
    image.write_bytes(b"fake-jpeg-content")

    receipt = PaymentReceipt(
        storage_path=str(image),
        mime_type="image/jpeg",
        original_filename="comprovante.jpg",
    )

    client = FakeOpenAIClient()
    analyzer = PixReceiptAnalyzer(client=client)

    extracted, usage = analyzer.analyze_with_usage(
        receipt=receipt
    )

    assert extracted["amount"] == 50.00
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 20

    content = client.responses.last_request["input"][0]["content"]
    image_input = content[1]

    assert image_input["type"] == "input_image"
    assert image_input["image_url"].startswith(
        "data:image/jpeg;base64,"
    )


def test_pix_analyzer_pdf_uses_base64_data_uri(tmp_path):
    raw_pdf = b"%PDF-1.4\nfake-pdf\n%%EOF"
    pdf = tmp_path / "comprovante.pdf"
    pdf.write_bytes(raw_pdf)

    receipt = PaymentReceipt(
        storage_path=str(pdf),
        mime_type="application/pdf",
        original_filename="comprovante.pdf",
    )

    client = FakeOpenAIClient()
    analyzer = PixReceiptAnalyzer(client=client)

    extracted, usage = analyzer.analyze_with_usage(
        receipt=receipt
    )

    assert extracted["is_pix_receipt"] is True
    assert usage["total_tokens"] == 120

    content = client.responses.last_request["input"][0]["content"]
    file_input = content[1]

    assert file_input["type"] == "input_file"
    assert file_input["filename"] == "comprovante.pdf"

    prefix = "data:application/pdf;base64,"
    assert file_input["file_data"].startswith(prefix)

    encoded = file_input["file_data"][len(prefix):]
    assert base64.b64decode(encoded) == raw_pdf


def test_pix_analyzer_analyze_still_returns_only_extracted_data(
    tmp_path,
):
    image = tmp_path / "comprovante.png"
    image.write_bytes(b"fake-png-content")

    receipt = PaymentReceipt(
        storage_path=str(image),
        mime_type="image/png",
        original_filename="comprovante.png",
    )

    analyzer = PixReceiptAnalyzer(
        client=FakeOpenAIClient()
    )

    result = analyzer.analyze(receipt=receipt)

    assert isinstance(result, dict)
    assert result["transaction_id"] == "TESTE-E2E"


def test_pix_validation_persists_usage_and_ai_event():
    from sqlalchemy import select

    from app.models.conversation import AIEvent

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    company = Company(name="Old Burguer 87")
    db.add(company)
    db.flush()

    store = Store(
        company_id=company.id,
        name="Old Burguer 87",
        slug=f"old-telemetry-{uuid4()}",
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

    order = Order(
        store_id=store.id,
        customer_id=uuid4(),
        cart_id=uuid4(),
        display_id="009999",
        status="PLACED",
        service_mode="TAKEOUT",
        payment_method="MIXED",
        payment_type="PENDING",
        subtotal=Decimal("65.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("65.00"),
        customer_name="Cliente Telemetria",
        customer_phone="5597999999999",
    )
    db.add(order)
    db.flush()

    db.add_all(
        [
            OrderPayment(
                order_id=order.id,
                method="PIX",
                payment_type="PREPAID",
                amount=Decimal("30.00"),
                position=1,
            ),
            OrderPayment(
                order_id=order.id,
                method="CASH",
                payment_type="PENDING",
                amount=Decimal("35.00"),
                position=2,
            ),
        ]
    )
    db.flush()

    receipt = PaymentReceipt(
        store_id=store.id,
        order_id=order.id,
        external_media_id="media-telemetria",
        media_type="IMAGE",
        mime_type="image/png",
        file_sha256="c" * 64,
        status="RECEIVED",
        validation_json={
            "candidate_orders": ["009999"],
        },
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    class FakeAnalyzerWithUsage(FakeAnalyzer):
        def analyze_with_usage(self, *, receipt):
            extracted = self.analyze(receipt=receipt)
            usage = {
                "model": "gpt-5.5-2026-04-23",
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "uncached_input_tokens": 60,
                "output_tokens": 20,
                "reasoning_tokens": 5,
                "total_tokens": 120,
                "estimated_cost_usd": "0.00123456",
            }
            return extracted, usage

    result = PixReceiptValidationService(
        analyzer=FakeAnalyzerWithUsage(
            "E2E-TELEMETRIA-UNICO-123",
            amount=30.00,
        )
    ).process(
        db,
        receipt=receipt,
    )

    assert result.status == "AUTO_CONFIRMED"
    assert result.validation_json["checks"]["amount_match"] is True
    assert result.validation_json["checks"]["amount_expected"] == "30.00"

    saved_usage = result.validation_json["usage"]
    assert saved_usage["input_tokens"] == 100
    assert saved_usage["output_tokens"] == 20
    assert saved_usage["estimated_cost_usd"] == "0.00123456"

    events = list(
        db.scalars(
            select(AIEvent).where(
                AIEvent.store_id == store.id,
                AIEvent.event_type == "PIX_AI_ANALYSIS",
            )
        ).all()
    )

    assert len(events) == 1

    event = events[0]

    assert event.conversation_id is None
    assert event.tool_name == "pix_receipt_validation"
    assert event.success is True
    assert event.payload_json["receipt_id"] == str(receipt.id)
    assert event.payload_json["order_id"] == str(order.id)
    assert event.payload_json["order_display_id"] == "009999"
    assert event.payload_json["decision"] == "AUTO_CONFIRMED"
    assert event.payload_json["usage"]["input_tokens"] == 100
    assert (
        event.payload_json["usage"]["estimated_cost_usd"]
        == "0.00123456"
    )

    db.close()
