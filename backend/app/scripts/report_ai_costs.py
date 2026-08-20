from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models.catalog import Store
from app.models.conversation import AIEvent
from app.models.order import Order


HOURS = 24

now = datetime.now(timezone.utc)
since = now - timedelta(hours=HOURS)

with SessionLocal() as db:
    store = db.scalar(
        select(Store).where(
            Store.name == "Old Burguer 87",
            Store.active.is_(True),
        )
    )

    if not store:
        raise SystemExit("Loja nao encontrada")

    events = list(
        db.scalars(
            select(AIEvent).where(
                AIEvent.store_id == store.id,
                AIEvent.event_type.in_(
                    ["AI_RESPONSE", "PIX_AI_ANALYSIS"]
                ),
                AIEvent.created_at >= since,
            )
        ).all()
    )

    calls = 0
    input_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    total_tokens = 0
    cost = Decimal("0")
    conversations = set()

    for event in events:
        payload = event.payload_json or {}
        usage = payload.get("usage")

        if not isinstance(usage, dict):
            continue

        calls += 1
        input_tokens += int(usage.get("input_tokens") or 0)
        cached_tokens += int(usage.get("cached_input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        reasoning_tokens += int(usage.get("reasoning_tokens") or 0)
        total_tokens += int(usage.get("total_tokens") or 0)

        raw_cost = usage.get("estimated_cost_usd")
        if raw_cost:
            cost += Decimal(str(raw_cost))

        if event.conversation_id:
            conversations.add(event.conversation_id)

    orders = db.scalar(
        select(func.count())
        .select_from(Order)
        .where(
            Order.store_id == store.id,
            Order.created_at >= since,
        )
    ) or 0

    print("====================================")
    print("CUSTO IA - ULTIMAS 24 HORAS")
    print("====================================")
    print("Chamadas OpenAI:", calls)
    print("Conversas:", len(conversations))
    print("Pedidos criados:", orders)
    print()
    print("Input tokens:", input_tokens)
    print("Cached tokens:", cached_tokens)
    print("Output tokens:", output_tokens)
    print("Reasoning tokens:", reasoning_tokens)
    print("Total tokens:", total_tokens)
    print()
    print("Custo estimado: US$", cost.quantize(Decimal("0.0001")))

    if conversations:
        print(
            "Custo / conversa: US$",
            (cost / len(conversations)).quantize(Decimal("0.0001")),
        )

    if orders:
        print(
            "Custo / pedido: US$",
            (cost / orders).quantize(Decimal("0.0001")),
        )

    print("====================================")
