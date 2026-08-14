import json
import time
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.olivia_prompt import OLIVIA_INSTRUCTIONS
from app.ai.providers.base import AIProvider
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import OliviaToolRegistry
from app.core.config import settings
from app.models.catalog import Store
from app.models.menu import StoreMenuDocument
from app.models.order import Order
from app.repositories.conversation import ConversationRepository
from app.repositories.customer import CustomerRepository
from app.schemas.conversation import AIEventCreate, MessageCreate
from app.services.conversation import ConversationService
from app.services.commercial_context import CommercialContextService


class OliviaExecutionError(RuntimeError):
    pass


def _nullable_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(schema)
    schema_type = result.get("type")

    if isinstance(schema_type, str):
        if schema_type != "null":
            result["type"] = [schema_type, "null"]
    elif isinstance(schema_type, list):
        if "null" not in schema_type:
            result["type"] = [*schema_type, "null"]
    elif "anyOf" in result:
        result["anyOf"] = [*result["anyOf"], {"type": "null"}]
    elif "oneOf" in result:
        result["oneOf"] = [*result["oneOf"], {"type": "null"}]
    else:
        return {"anyOf": [result, {"type": "null"}]}

    if "enum" in result and None not in result["enum"]:
        result["enum"] = [*result["enum"], None]

    return result


def _responses_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(schema)

    properties = result.get("properties")
    schema_type = result.get("type")
    is_object = schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )

    if is_object and isinstance(properties, dict):
        originally_required = set(result.get("required") or [])
        normalized_properties: dict[str, Any] = {}

        for name, property_schema in properties.items():
            normalized = _responses_tool_schema(property_schema)
            if name not in originally_required:
                normalized = _nullable_schema(normalized)
            normalized_properties[name] = normalized

        result["properties"] = normalized_properties
        result["required"] = list(properties.keys())
        result["additionalProperties"] = False

    if isinstance(result.get("items"), dict):
        result["items"] = _responses_tool_schema(result["items"])

    for keyword in ("anyOf", "oneOf", "allOf"):
        if isinstance(result.get(keyword), list):
            result[keyword] = [
                _responses_tool_schema(item) if isinstance(item, dict) else item
                for item in result[keyword]
            ]

    return result


def _drop_null_arguments(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_null_arguments(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_drop_null_arguments(item) for item in value]
    return value


def _store_context(db: Session, *, store_id: UUID) -> str:
    store = db.scalar(select(Store).where(Store.id == store_id))
    if store is None:
        return "REGRAS DA LOJA: loja não encontrada; não invente regras comerciais."

    if store.slug == "old-burguer-87":
        return (
            "REGRAS COMERCIAIS APROVADAS DA OLD BURGUER 87: "
            "para ENTREGA, o pedido mínimo é R$ 15,00 somente em produtos, antes da taxa; "
            "a taxa fixa de entrega é R$ 3,00; "
            "a taxa não conta para atingir o pedido mínimo; "
            "se o subtotal em produtos estiver abaixo de R$ 15,00, informe exatamente quanto falta e ofereça produtos do catálogo para completar; "
            "não pergunte pagamento enquanto o subtotal de entrega estiver abaixo do mínimo; "
            "quando o subtotal atingir pelo menos R$ 15,00, informe a taxa de R$ 3,00 diretamente, sem consultar equipe humana; "
            "para RETIRADA não há taxa de entrega nem pedido mínimo de entrega."
        )

    return (
        f"REGRAS DA LOJA {store.name}: use somente regras comerciais fornecidas por ferramentas ou contexto; "
        "não invente pedido mínimo nem taxa de entrega."
    )


def _menu_pdf_context(db: Session, *, store_id: UUID) -> str:
    document = db.scalar(
        select(StoreMenuDocument).where(
            StoreMenuDocument.store_id == store_id
        )
    )

    if document is None:
        return (
            "CONTEXTO DO CARDÁPIO PDF: não existe PDF cadastrado neste momento. "
            "Se o cliente pedir PDF, use send_menu_pdf mesmo assim para confirmar "
            "a indisponibilidade pela ferramenta oficial."
        )

    return (
        "CONTEXTO DO CARDÁPIO PDF: existe PDF oficial cadastrado e disponível "
        f"para envio pelo WhatsApp. Arquivo: {document.original_name}. "
        "Quando o cliente pedir explicitamente o cardápio em PDF, use "
        "send_menu_pdf imediatamente. Não use search_knowledge nem "
        "request_human_help antes dessa ferramenta."
    )


def _local_time_context() -> str:
    """Informa à Olívia a hora local de Coari/AM e a saudação adequada."""
    now = datetime.now(ZoneInfo("America/Manaus"))

    if 5 <= now.hour < 12:
        greeting = "Bom dia"
    elif 12 <= now.hour < 18:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"

    return (
        "CONTEXTO LOCAL DA OLD BURGUER 87: "
        f"data e hora atual em Coari/AM: {now.strftime('%d/%m/%Y %H:%M')}. "
        f"Saudação adequada neste momento: {greeting}. "
        "Use essa saudação somente quando for natural, principalmente no início "
        "da conversa ou quando o cliente cumprimentar. Não repita a saudação "
        "desnecessariamente em todas as mensagens."
    )


def _customer_context(
    db: Session,
    *,
    store_id: UUID,
    customer_phone: str | None,
) -> str:
    if not customer_phone:
        return "CANAL: telefone do cliente não disponível."

    customer = CustomerRepository().get_by_phone(
        db,
        store_id=store_id,
        phone=customer_phone,
    )
    if customer is None:
        return (
            "CONTEXTO DO CLIENTE: cliente ainda não cadastrado. "
            "O telefone do WhatsApp já é conhecido pelo sistema; não peça o telefone. "
            "Peça somente o nome quando precisar criar o cadastro."
        )

    addresses = [address for address in customer.addresses if address.active]
    if addresses:
        address_text = "; ".join(
            f"{address.label}: {address.street}, {address.number}, "
            f"{address.neighborhood}, {address.city}-{address.state}"
            + (f", compl. {address.complement}" if address.complement else "")
            + (f", ref. {address.reference}" if address.reference else "")
            for address in addresses[:3]
        )
    else:
        address_text = "nenhum endereço salvo"

    recent_orders = list(
        db.scalars(
            select(Order)
            .where(
                Order.store_id == store_id,
                Order.customer_id == customer.id,
            )
            .order_by(Order.created_at.desc())
            .limit(3)
        ).all()
    )
    if recent_orders:
        order_text = "; ".join(
            f"pedido {order.display_id}: "
            f"{', '.join(f'{item.quantity}x {item.product_name}' for item in order.items)}; "
            f"modo={order.service_mode}; pagamento={order.payment_method}"
            for order in recent_orders
        )
    else:
        order_text = "nenhum pedido anterior"

    return (
        "CONTEXTO DO CLIENTE JÁ CADASTRADO: "
        f"nome={customer.name}; telefone já conhecido pelo canal; "
        f"endereços={address_text}; últimos pedidos={order_text}. "
        "Não peça novamente nome ou telefone. Para entrega, ofereça endereço salvo antes de pedir outro. "
        "Use pedidos anteriores apenas para facilitar sugestões; nunca repita item, pagamento ou endereço sem confirmação."
    )


class OliviaOrchestrator:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider
        self.conversations = ConversationService()
        self.repository = ConversationRepository()

    def reply(
        self,
        db: Session,
        *,
        store_id: UUID,
        conversation_id: UUID,
        customer_message: str,
        customer_phone: str | None = None,
        record_customer_message: bool = True,
        extra_instructions: str | None = None,
        excluded_tools: set[str] | None = None,
    ) -> str:
        conversation = self.repository.get(db, conversation_id)
        if conversation is None or conversation.store_id != store_id:
            raise OliviaExecutionError("Conversa não encontrada para esta loja.")

        if record_customer_message:
            self.conversations.add_message(
                db,
                conversation_id=conversation_id,
                payload=MessageCreate(
                    direction="INBOUND",
                    sender_type="CUSTOMER",
                    content=customer_message,
                ),
            )

        history = self.repository.list_messages(db, conversation_id, limit=30)
        input_items = [
            {
                "role": "user" if message.sender_type == "CUSTOMER" else "assistant",
                "content": message.content,
            }
            for message in history
        ]
        registry = OliviaToolRegistry(
            ToolContext(
                db=db,
                store_id=store_id,
                conversation_id=conversation_id,
                customer_phone=customer_phone,
            )
        )
        instructions = (
            OLIVIA_INSTRUCTIONS
            + "\n\n"
            + CommercialContextService().build(db, store_id)
            + "\n\n"
            + _menu_pdf_context(db, store_id=store_id)
            + "\n\n"
            + _local_time_context()
            + "\n\n"
            + _customer_context(
                db,
                store_id=store_id,
                customer_phone=customer_phone,
            )
        )
        if extra_instructions:
            instructions += "\n\n" + extra_instructions

        blocked_tools = excluded_tools or set()
        available_tools = [
            tool
            for tool in self._provider_tools(registry)
            if tool["name"] not in blocked_tools
        ]

        previous_response_id = None

        for round_number in range(1, settings.olivia_max_tool_rounds + 1):
            started = time.perf_counter()
            response = self.provider.respond(
                instructions=instructions,
                input_items=input_items,
                tools=available_tools,
                previous_response_id=previous_response_id,
            )
            previous_response_id = response.response_id
            self.conversations.record_event(
                db,
                store_id=store_id,
                payload=AIEventCreate(
                    conversation_id=conversation_id,
                    event_type="AI_RESPONSE",
                    success=True,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    payload_json={
                        "round": round_number,
                        "tool_calls": len(response.tool_calls),
                    },
                ),
            )

            if response.tool_calls:
                outputs = []
                for call in response.tool_calls:
                    tool_started = time.perf_counter()
                    try:
                        arguments = _drop_null_arguments(call.arguments)
                        result = registry.execute(call.name, arguments)
                        payload = {
                            "ok": result.ok,
                            "data": result.data,
                            "error": result.error,
                            "requires_human": result.requires_human,
                        }
                        success = result.ok
                    except Exception as error:
                        payload = {
                            "ok": False,
                            "error": str(error),
                            "requires_human": True,
                        }
                        success = False

                    self.conversations.record_event(
                        db,
                        store_id=store_id,
                        payload=AIEventCreate(
                            conversation_id=conversation_id,
                            event_type="TOOL_EXECUTION",
                            tool_name=call.name,
                            success=success,
                            duration_ms=int(
                                (time.perf_counter() - tool_started) * 1000
                            ),
                            payload_json={
                                "arguments": call.arguments,
                                "result": payload,
                            },
                            error_message=None if success else payload.get("error"),
                        ),
                    )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(
                                payload,
                                ensure_ascii=False,
                                default=str,
                            ),
                        }
                    )
                input_items = outputs
                continue

            if response.text:
                self.conversations.add_message(
                    db,
                    conversation_id=conversation_id,
                    payload=MessageCreate(
                        direction="OUTBOUND",
                        sender_type="OLIVIA",
                        content=response.text,
                    ),
                )
                return response.text

            raise OliviaExecutionError(
                "O provedor não retornou texto nem chamada de ferramenta."
            )

        raise OliviaExecutionError(
            "A Olívia excedeu o limite de chamadas de ferramentas."
        )

    @staticmethod
    def _provider_tools(registry: OliviaToolRegistry) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": definition.name,
                "description": definition.description,
                "parameters": _responses_tool_schema(definition.input_schema),
                "strict": False,
            }
            for definition in registry.definitions()
        ]
