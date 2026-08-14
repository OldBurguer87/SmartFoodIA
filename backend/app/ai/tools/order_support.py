from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.tools.context import ToolContext
from app.ai.tools.contracts import ToolDefinition, ToolResult
from app.models.commercial import StoreCommercialRules
from app.models.order import Order, OrderItem
from app.schemas.conversation import HumanTicketCreate
from app.services.conversation import ConversationService
from app.services.human_relay import HumanRelayService


STATUS_LABELS = {
    "READY_FOR_INTEGRATION": "Pedido recebido e aguardando confirmação",
    "CONFIRMED": "Pedido confirmado e em preparação",
    "READY": "Pedido pronto",
    "DISPATCHED": "Pedido saiu para entrega",
    "CONCLUDED": "Pedido finalizado",
    "CANCELLED": "Pedido cancelado",
}


def normalize_order_number(value: str | None) -> str | None:
    if not value:
        return None

    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits:
        return None

    return digits.zfill(6)


def load_customer_order(
    context: ToolContext,
    *,
    order_number: str | None = None,
) -> Order | None:
    if not context.customer_phone:
        return None

    statement = (
        select(Order)
        .where(
            Order.store_id == context.store_id,
            Order.customer_phone == context.customer_phone,
        )
        .options(
            selectinload(Order.items).selectinload(OrderItem.modifiers),
            selectinload(Order.events),
        )
    )

    normalized = normalize_order_number(order_number)

    if normalized:
        statement = statement.where(Order.display_id == normalized)
    else:
        statement = statement.order_by(Order.created_at.desc()).limit(1)

    return context.db.scalar(statement)


def order_payload(context: ToolContext, order: Order) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    created_at = order.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    elapsed_minutes = max(
        0,
        int((now - created_at).total_seconds() // 60),
    )

    rules = context.db.scalar(
        select(StoreCommercialRules).where(
            StoreCommercialRules.store_id == context.store_id
        )
    )

    average_prep_minutes = (
        rules.average_prep_minutes
        if rules is not None
        else None
    )

    delay_assessment = None
    overdue_minutes = None

    if (
        average_prep_minutes is not None
        and order.status in {"READY_FOR_INTEGRATION", "CONFIRMED"}
    ):
        if elapsed_minutes > average_prep_minutes:
            delay_assessment = "OVER_PREP_ESTIMATE"
            overdue_minutes = elapsed_minutes - average_prep_minutes
        else:
            delay_assessment = "WITHIN_PREP_ESTIMATE"

    elif order.status == "READY":
        delay_assessment = (
            "READY_WAITING_DISPATCH"
            if order.service_mode == "DELIVERY"
            else "READY_FOR_PICKUP"
        )

    elif order.status == "DISPATCHED":
        # Não há ETA de entregador disponível hoje.
        delay_assessment = "OUT_FOR_DELIVERY_NO_ETA"

    elif order.status == "CONCLUDED":
        delay_assessment = "CONCLUDED"

    elif order.status == "CANCELLED":
        delay_assessment = "CANCELLED"

    latest_event = None
    if order.events:
        latest_event = max(
            order.events,
            key=lambda item: item.created_at,
        )

    return {
        "order_id": str(order.id),
        "display_id": order.display_id,
        "status": order.status,
        "status_label": STATUS_LABELS.get(
            order.status,
            order.status,
        ),
        "service_mode": order.service_mode,
        "created_at": order.created_at.isoformat(),
        "elapsed_minutes": elapsed_minutes,
        "average_prep_minutes": average_prep_minutes,
        "delay_assessment": delay_assessment,
        "overdue_minutes": overdue_minutes,
        "consumer_order_id": order.consumer_order_id,
        "payment_method": order.payment_method,
        "payment_type": order.payment_type,
        "subtotal": float(order.subtotal),
        "delivery_fee": float(order.delivery_fee),
        "discount": float(order.discount),
        "total": float(order.total),
        "customer_name": order.customer_name,
        "address": (
            {
                "street": order.address_street,
                "number": order.address_number,
                "neighborhood": order.address_neighborhood,
                "city": order.address_city,
                "state": order.address_state,
                "complement": order.address_complement,
                "reference": order.address_reference,
            }
            if order.address_street
            else None
        ),
        "items": [
            {
                "name": item.product_name,
                "quantity": item.quantity,
                "observations": item.observations,
                "modifiers": [
                    {
                        "name": modifier.modifier_name,
                        "quantity": modifier.quantity,
                    }
                    for modifier in item.modifiers
                ],
            }
            for item in order.items
        ],
        "latest_event": (
            {
                "code": latest_event.code,
                "full_code": latest_event.full_code,
                "status": latest_event.status,
                "reason": latest_event.reason,
                "created_at": latest_event.created_at.isoformat(),
            }
            if latest_event
            else None
        ),
    }


class GetOrderStatusTool:
    definition = ToolDefinition(
        name="get_order_status",
        description=(
            "Consulta o pedido real do cliente e seu status atual. "
            "Use antes de responder perguntas sobre demora, entrega, retirada, "
            "cancelamento, pedido finalizado ou qualquer problema pós-pedido. "
            "Se order_number não for informado, consulta o pedido mais recente "
            "do telefone atual do WhatsApp."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_number": {
                    "type": ["string", "null"],
                    "description": (
                        "Número visível do pedido, como 000022 ou 22. "
                        "Pode ser omitido para consultar o mais recente."
                    ),
                },
            },
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    def execute(
        self,
        *,
        order_number: str | None = None,
        **_: Any,
    ) -> ToolResult:
        order = load_customer_order(
            self.context,
            order_number=order_number,
        )

        if order is None:
            return ToolResult(
                ok=False,
                error=(
                    "Não foi possível localizar um pedido desse cliente "
                    "no histórico da Old Burguer 87."
                ),
            )

        return ToolResult(
            ok=True,
            data=order_payload(self.context, order),
        )


class ReportOrderIssueTool:
    definition = ToolDefinition(
        name="report_order_issue",
        description=(
            "Abre um chamado operacional relacionado a um pedido e encaminha "
            "a conversa para atendimento humano pelo mesmo canal de suporte. "
            "Use para atraso que precisa intervenção, item errado ou faltando, "
            "qualidade, pedido não recebido, cobrança/pagamento, solicitação "
            "de cancelamento ou outro problema pós-pedido. "
            "Não cria lacuna de conhecimento."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "issue_type": {
                    "type": "string",
                    "enum": [
                        "DELAY",
                        "WRONG_ITEM",
                        "MISSING_ITEM",
                        "QUALITY",
                        "NOT_RECEIVED",
                        "PAYMENT",
                        "CANCELLATION",
                        "OTHER",
                    ],
                },
                "customer_message": {
                    "type": "string",
                    "minLength": 1,
                },
                "order_number": {
                    "type": ["string", "null"],
                },
                "details": {
                    "type": ["string", "null"],
                },
            },
            "required": [
                "issue_type",
                "customer_message",
            ],
            "additionalProperties": False,
        },
    )

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.conversations = ConversationService()
        self.relay = HumanRelayService()

    def execute(
        self,
        *,
        issue_type: str,
        customer_message: str,
        order_number: str | None = None,
        details: str | None = None,
        **_: Any,
    ) -> ToolResult:
        order = load_customer_order(
            self.context,
            order_number=order_number,
        )

        category_map = {
            "DELAY": "DELIVERY",
            "WRONG_ITEM": "OTHER",
            "MISSING_ITEM": "OTHER",
            "QUALITY": "OTHER",
            "NOT_RECEIVED": "DELIVERY",
            "PAYMENT": "PAYMENT",
            "CANCELLATION": "OTHER",
            "OTHER": "OTHER",
        }

        priority_map = {
            "DELAY": "HIGH",
            "WRONG_ITEM": "HIGH",
            "MISSING_ITEM": "HIGH",
            "QUALITY": "HIGH",
            "NOT_RECEIVED": "URGENT",
            "PAYMENT": "URGENT",
            "CANCELLATION": "HIGH",
            "OTHER": "NORMAL",
        }

        category = category_map.get(issue_type, "OTHER")
        priority = priority_map.get(issue_type, "NORMAL")

        order_label = (
            f"Pedido #{order.display_id}"
            if order is not None
            else "Pedido não localizado automaticamente"
        )

        status_label = (
            STATUS_LABELS.get(order.status, order.status)
            if order is not None
            else "status não disponível"
        )

        reason_parts = [
            order_label,
            f"tipo={issue_type}",
            f"status={status_label}",
        ]

        if details:
            reason_parts.append(details.strip())

        reason = " | ".join(reason_parts)

        # Limite do campo reason do ticket.
        reason = reason[:500]

        ticket = self.conversations.create_ticket(
            self.context.db,
            store_id=self.context.store_id,
            payload=HumanTicketCreate(
                conversation_id=self.context.conversation_id,
                customer_id=(
                    order.customer_id
                    if order is not None
                    else None
                ),
                category=category,
                priority=priority,
                reason=reason,
                customer_message=customer_message,
            ),
        )

        staff_notified = 0

        if self.context.conversation_id is not None:
            self.conversations.wait_for_human(
                self.context.db,
                conversation_id=self.context.conversation_id,
                reason=reason,
                ticket_id=ticket.id,
            )

            staff_notified = self.relay.notify_waiting(
                self.context.db,
                store_id=self.context.store_id,
                conversation_id=self.context.conversation_id,
                reason=reason,
            )

        return ToolResult(
            ok=True,
            requires_human=True,
            data={
                "ticket_id": str(ticket.id),
                "issue_type": issue_type,
                "priority": priority,
                "category": category,
                "order_id": (
                    str(order.id)
                    if order is not None
                    else None
                ),
                "order_number": (
                    order.display_id
                    if order is not None
                    else normalize_order_number(order_number)
                ),
                "order_status": (
                    order.status
                    if order is not None
                    else None
                ),
                "order_status_label": (
                    STATUS_LABELS.get(order.status, order.status)
                    if order is not None
                    else None
                ),
                "staff_notified": staff_notified,
            },
        )
