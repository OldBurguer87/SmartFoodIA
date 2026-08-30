from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.pix_shift_closing import (
    PixShiftClosingService,
    PixShiftSummary,
)


TZ = ZoneInfo("America/Manaus")


class FakeRows(list):
    def all(self):
        return list(self)


class SummaryDB:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return FakeRows(self.rows)


class HoursDB:
    def __init__(self, hours):
        self.hours = hours

    def scalar(self, _statement):
        return self.hours


class StoreDB:
    def __init__(self, store):
        self.store = store

    def scalar(self, _statement):
        return self.store


class FakeChannels:
    def __init__(self, account):
        self.account = account
        self.created = []

    def get_account_by_store(
        self,
        db,
        *,
        store_id,
        provider,
    ):
        return self.account

    def create_outbound(
        self,
        db,
        *,
        account,
        conversation_id,
        recipient,
        content,
    ):
        message = SimpleNamespace(
            channel_account_id=account.id,
            recipient=recipient,
            content=content,
        )
        self.created.append(message)
        return message


def test_summary_counts_confirmed_pending_and_fallback():
    service = PixShiftClosingService()

    order_manual = SimpleNamespace(
        id=uuid4(),
        total=Decimal("44.90"),
    )
    order_auto = SimpleNamespace(
        id=uuid4(),
        total=Decimal("33.00"),
    )
    order_pending = SimpleNamespace(
        id=uuid4(),
        total=Decimal("20.00"),
    )

    rows = [
        (
            SimpleNamespace(
                status="HUMAN_CONFIRMED",
                extracted_amount=None,
            ),
            order_manual,
        ),
        (
            SimpleNamespace(
                status="AUTO_CONFIRMED",
                extracted_amount=Decimal("33.00"),
            ),
            order_auto,
        ),
        # Uma revisão posterior do mesmo pedido não pode
        # transformar o pedido já confirmado em pendência.
        (
            SimpleNamespace(
                status="NEEDS_REVIEW",
                extracted_amount=None,
            ),
            order_auto,
        ),
        (
            SimpleNamespace(
                status="NEEDS_REVIEW",
                extracted_amount=None,
            ),
            order_pending,
        ),
    ]

    db = SummaryDB(rows)

    start = datetime(
        2026, 8, 20, 17, 0,
        tzinfo=TZ,
    )
    end = datetime(
        2026, 8, 20, 23, 59,
        tzinfo=TZ,
    )

    summary = service.build_summary(
        db,
        store_id=uuid4(),
        shift_date=date(2026, 8, 20),
        start_local=start,
        end_local=end,
    )

    assert summary.confirmed_orders == 2
    assert summary.auto_confirmed == 1
    assert summary.human_confirmed == 1
    assert summary.pending_review == 1
    assert summary.fallback_values == 1
    assert summary.total == Decimal("77.90")

    sql = str(db.statement)

    # O pedido é que precisa pertencer ao turno.
    assert "orders.created_at" in sql

    # Apenas PIX.
    assert "orders.payment_method" in sql

    # O comprovante possui corte próprio para a tolerância
    # após o encerramento.
    assert "payment_receipts.created_at" in sql


def test_closing_becomes_due_only_after_five_minute_grace():
    service = PixShiftClosingService()

    hours = SimpleNamespace(
        closed=False,
        open_time=time(17, 0),
        close_time=time(23, 59),
    )

    store = SimpleNamespace(
        id=uuid4(),
        timezone="America/Manaus",
    )

    db = HoursDB(hours)

    before = datetime(
        2026, 8, 21, 4, 3, 59,
        tzinfo=timezone.utc,
    )

    at_grace = datetime(
        2026, 8, 21, 4, 4, 0,
        tzinfo=timezone.utc,
    )

    assert (
        service._find_due_shift(
            db,
            store=store,
            now=before,
        )
        is None
    )

    due = service._find_due_shift(
        db,
        store=store,
        now=at_grace,
    )

    assert due is not None

    shift_date, _, start_local, end_local = due

    assert shift_date == date(2026, 8, 20)
    assert start_local.hour == 17
    assert end_local.hour == 23
    assert end_local.minute == 59


def test_message_contains_financial_summary():
    service = PixShiftClosingService()

    store = SimpleNamespace(
        name="Old Burguer 87",
    )

    summary = PixShiftSummary(
        shift_date=date(2026, 8, 20),
        start_local=datetime(
            2026, 8, 20, 17, 0,
            tzinfo=TZ,
        ),
        end_local=datetime(
            2026, 8, 20, 23, 59,
            tzinfo=TZ,
        ),
        confirmed_orders=4,
        auto_confirmed=1,
        human_confirmed=3,
        pending_review=0,
        fallback_values=3,
        total=Decimal("127.91"),
    )

    message = service.format_message(
        store=store,
        summary=summary,
    )

    assert "PIX confirmados: 4" in message
    assert "Automáticos: 1" in message
    assert "Confirmados pela equipe: 3" in message
    assert "Total PIX recebido: R$ 127,91" in message
    assert "Pendentes de conferência: 0" in message
    assert "PIX-SHIFT-20260820" in message


def test_run_once_is_idempotent_for_each_recipient():
    service = PixShiftClosingService()

    store = SimpleNamespace(
        id=uuid4(),
        slug="old-burguer-87",
        name="Old Burguer 87",
        timezone="America/Manaus",
    )

    account = SimpleNamespace(
        id=uuid4(),
    )

    members = [
        SimpleNamespace(
            id=uuid4(),
            phone="5597000000001",
        ),
        SimpleNamespace(
            id=uuid4(),
            phone="5597000000002",
        ),
    ]

    hours = SimpleNamespace(
        closed=False,
        open_time=time(17, 0),
        close_time=time(23, 59),
    )

    start_local = datetime(
        2026, 8, 20, 17, 0,
        tzinfo=TZ,
    )
    end_local = datetime(
        2026, 8, 20, 23, 59,
        tzinfo=TZ,
    )

    summary = PixShiftSummary(
        shift_date=date(2026, 8, 20),
        start_local=start_local,
        end_local=end_local,
        confirmed_orders=4,
        auto_confirmed=1,
        human_confirmed=3,
        pending_review=0,
        fallback_values=3,
        total=Decimal("127.91"),
    )

    fake_channels = FakeChannels(account)
    service.channels = fake_channels

    service._find_due_shift = lambda db, store, now: (
        date(2026, 8, 20),
        hours,
        start_local,
        end_local,
    )

    service._recipients = lambda db, store_id: members

    service.build_summary = lambda *args, **kwargs: summary

    def existing_snapshot(
        db,
        *,
        account_id,
        marker,
    ):
        if not fake_channels.created:
            return None
        return fake_channels.created[0]

    service._existing_snapshot = existing_snapshot

    def already_queued(
        db,
        *,
        account_id,
        recipient,
        marker,
    ):
        return any(
            message.recipient == recipient
            and marker in message.content
            for message in fake_channels.created
        )

    service._already_queued_for_recipient = already_queued

    db = StoreDB(store)

    now = datetime(
        2026, 8, 21, 4, 4,
        tzinfo=timezone.utc,
    )

    first = service.run_once(
        db,
        now=now,
    )

    assert first.queued_messages == 2
    assert first.already_queued == 0
    assert len(fake_channels.created) == 2

    second = service.run_once(
        db,
        now=now,
    )

    assert second.queued_messages == 0
    assert second.already_queued == 2
    assert len(fake_channels.created) == 2
