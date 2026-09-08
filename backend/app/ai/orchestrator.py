import json
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta
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
from app.models.commercial import StoreCommercialRules
from app.models.catalog_version import CatalogVersion
from app.models.menu import StoreMenuDocument
from app.models.order import Order
from app.models.conversation import AIEvent
from app.repositories.catalog import ProductRepository
from app.services.catalog.search import normalize_text
from app.repositories.cart import CartRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.customer import CustomerRepository
from app.schemas.conversation import AIEventCreate, MessageCreate
from app.services.cart import CartService
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
            "Se houver uma solicitação ampla de cardápio, send_menu_pdf pode ser "
            "tentada como ferramenta oficial; se retornar indisponibilidade, "
            "use o catálogo como fallback."
        )

    active_catalog = db.scalar(
        select(CatalogVersion)
        .where(
            CatalogVersion.store_id == store_id,
            CatalogVersion.active.is_(True),
        )
        .order_by(CatalogVersion.created_at.desc())
        .limit(1)
    )

    synchronized = bool(
        active_catalog is not None
        and document.catalog_version_id == active_catalog.id
    )

    if not synchronized:
        return (
            "CONTEXTO DO CARDÁPIO PDF: existe PDF cadastrado, mas ele NÃO está "
            "sincronizado com a versão ativa do catálogo. Não apresente esse "
            "PDF como cardápio atual. Use o catálogo como fallback até o PDF "
            "ser atualizado."
        )

    return (
        "CONTEXTO DO CARDÁPIO PDF: existe PDF oficial, atualizado e sincronizado "
        f"com a versão ativa do catálogo. Arquivo: {document.original_name}. "
        "Para solicitações amplas de cardápio, menu, categorias ou opções, "
        "priorize send_menu_pdf em vez de listar o catálogo pelo WhatsApp."
    )

def _local_greeting() -> str:
    now = datetime.now(ZoneInfo("America/Manaus"))

    if 5 <= now.hour < 12:
        return "Bom dia"

    if 12 <= now.hour < 18:
        return "Boa tarde"

    return "Boa noite"


def _customer_greeted(message: str) -> bool:
    value = message.strip().lower()

    return bool(
        re.match(
            r"^(oi\b|ol[aá]\b|opa\b|bom dia\b|boa tarde\b|boa noite\b)",
            value,
        )
    )


def _should_force_greeting(
    *,
    history,
    customer_message: str,
) -> bool:
    customer_messages = sum(
        1
        for message in history
        if message.sender_type == "CUSTOMER"
    )

    # Primeira mensagem da conversa ou cliente cumprimentou.
    return (
        customer_messages <= 1
        or _customer_greeted(customer_message)
    )


def _ensure_local_greeting(text: str) -> str:
    greeting = _local_greeting()
    result = text.strip()

    if result.lower().startswith(greeting.lower()):
        return result

    # Se o modelo usou uma saudação de período errada,
    # remove antes de colocar a correta.
    result = re.sub(
        r"^(bom dia|boa tarde|boa noite)\b[!,.:\-\s]*",
        "",
        result,
        flags=re.IGNORECASE,
    ).strip()

    if not result:
        return f"{greeting}!"

    return f"{greeting}! {result}"


def _local_time_context() -> str:
    """Informa à Olívia a hora local de Coari/AM e a saudação adequada."""
    now = datetime.now(ZoneInfo("America/Manaus"))

    greeting = _local_greeting()

    return (
        "CONTEXTO LOCAL DA OLD BURGUER 87: "
        f"data e hora atual em Coari/AM: {now.strftime('%d/%m/%Y %H:%M')}. "
        f"Saudação adequada neste momento: {greeting}. "
        "Use essa saudação somente quando for natural, principalmente no início "
        "da conversa ou quando o cliente cumprimentar. Não repita a saudação "
        "desnecessariamente em todas as mensagens."
    )


def _format_brl(value) -> str:
    try:
        formatted = f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "valor do pedido"

    formatted = (
        formatted
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    return f"R$ {formatted}"


def _pix_payment_instructions(
    db: Session,
    *,
    store_id: UUID,
    order_data: dict[str, Any],
) -> tuple[str | None, str | None]:
    rules = db.scalar(
        select(StoreCommercialRules).where(
            StoreCommercialRules.store_id == store_id
        )
    )

    if (
        rules is None
        or not rules.pix_key
        or not rules.pix_receiver_name
    ):
        return None, None

    lines = [
        "Para pagar via PIX:",
        f"Chave PIX: {rules.pix_key}",
        f"Recebedor: {rules.pix_receiver_name}",
    ]

    if rules.pix_receiver_institution:
        lines.append(
            f"Instituição: {rules.pix_receiver_institution}"
        )

    total = order_data.get("total")

    if total is not None:
        lines.append(
            f"Valor: {_format_brl(total)}"
        )

    lines.extend(
        [
            "",
            "Depois de pagar, envie o comprovante aqui no "
            "WhatsApp para eu conferir. 😊",
        ]
    )

    return "\n".join(lines), str(rules.pix_key)


def _ensure_pix_payment_instructions(
    text: str,
    *,
    instructions: str,
    pix_key: str,
) -> str:
    result = text.strip()
    lower = result.lower()

    key_present = pix_key.lower() in lower
    receipt_requested = "comprovante" in lower

    if key_present and receipt_requested:
        return result

    if key_present:
        return (
            result
            + "\n\n"
            + "Depois de pagar, envie o comprovante aqui no "
            "WhatsApp para eu conferir. 😊"
        )

    return result + "\n\n" + instructions


def _normalize_confirmation_text(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\sáàâãéêíóôõúç]", " ", value)
    return " ".join(value.split())


def _customer_confirms_order(value: str) -> bool:
    normalized = _normalize_confirmation_text(value)

    exact = {
        "sim",
        "sim pode",
        "pode",
        "confirmo",
        "confirmar",
        "pode confirmar",
        "pode confirmar sim",
        "sim confirma",
        "sim confirmar",
        "isso",
        "isso mesmo",
        "correto",
        "pode fechar",
        "fechar pedido",
        "pode finalizar",
    }

    return normalized in exact


def _assistant_was_asking_order_confirmation(history) -> bool:
    last_assistant = None

    for message in reversed(history):
        if message.sender_type == "OLIVIA":
            last_assistant = message.content
            break

    if not last_assistant:
        return False

    normalized = _normalize_confirmation_text(
        last_assistant
    )

    confirmation_phrases = (
        "pode confirmar o pedido",
        "posso confirmar o pedido",
        "confirma o pedido",
        "confirmar o pedido assim",
        "pode confirmar assim",
        "pode finalizar o pedido",
        "posso finalizar o pedido",
    )

    return any(
        phrase in normalized
        for phrase in confirmation_phrases
    )


def _checkout_required_by_customer(
    *,
    history,
    customer_message: str,
) -> bool:
    return (
        _customer_confirms_order(customer_message)
        and _assistant_was_asking_order_confirmation(history)
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

    addresses = [
        address
        for address in customer.addresses
        if address.active
    ]

    if addresses:
        address_text = "; ".join(
            f"address_id={address.id}; {address.label}: "
            f"{address.street}, {address.number}, "
            f"{address.neighborhood}, {address.city}-{address.state}"
            + (
                f", compl. {address.complement}"
                if address.complement
                else ""
            )
            + (
                f", ref. {address.reference}"
                if address.reference
                else ""
            )
            + (
                ", padrão=true"
                if address.is_default
                else ""
            )
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

    open_cart = CartRepository().get_open_for_customer(
        db,
        store_id=store_id,
        customer_id=customer.id,
    )

    if open_cart is not None:
        cart = CartService._to_dto(open_cart)

        if cart.items:
            item_rows = []

            for item in cart.items:
                modifiers = ", ".join(
                    f"{modifier.quantity}x {modifier.name} "
                    f"(codigo={modifier.external_code})"
                    for modifier in item.modifiers
                )

                item_text = (
                    f"item_id={item.id}; "
                    f"codigo={item.product_external_code}; "
                    f"{item.quantity}x {item.product_name}; "
                    f"unitario={item.unit_price}; "
                    f"total={item.total}"
                )

                if item.observations:
                    item_text += f"; observacao={item.observations}"

                if modifiers:
                    item_text += f"; adicionais=[{modifiers}]"

                item_rows.append(item_text)

            cart_items = " | ".join(item_rows)
        else:
            cart_items = "sem itens"

        cart_text = (
            f"cart_id={cart.id}; "
            f"modalidade={cart.service_mode}; "
            f"subtotal={cart.subtotal}; "
            f"itens=[{cart_items}]"
        )
    else:
        cart_text = "nenhum carrinho aberto"

    return (
        "CONTEXTO DO CLIENTE JÁ CADASTRADO: "
        f"customer_id={customer.id}; "
        f"nome={customer.name}; telefone já conhecido pelo canal; "
        f"endereços={address_text}; "
        f"últimos pedidos={order_text}. "
        "ESTADO OPERACIONAL ATUAL: "
        f"carrinho_aberto={cart_text}. "
        "Não peça novamente nome ou telefone. "
        "Para entrega, ofereça endereço salvo antes de pedir outro. "
        "Use pedidos anteriores apenas para facilitar sugestões; "
        "nunca repita item, pagamento ou endereço sem confirmação. "
        "Os IDs e dados do ESTADO OPERACIONAL ATUAL vieram diretamente "
        "do SmartFoodIA e podem ser reutilizados nas ferramentas quando "
        "continuarem válidos; não é necessário consultar novamente apenas "
        "para redescobrir esses mesmos identificadores."
    )


def _recent_validated_products_context(
    db: Session,
    *,
    store_id: UUID,
    conversation_id: UUID,
) -> str:
    cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=10)

    last_checkout = db.scalar(
        select(AIEvent)
        .where(
            AIEvent.store_id == store_id,
            AIEvent.conversation_id == conversation_id,
            AIEvent.event_type == "TOOL_EXECUTION",
            AIEvent.tool_name == "checkout_cart",
            AIEvent.success.is_(True),
        )
        .order_by(AIEvent.created_at.desc())
        .limit(1)
    )

    conditions = [
        AIEvent.store_id == store_id,
        AIEvent.conversation_id == conversation_id,
        AIEvent.event_type == "TOOL_EXECUTION",
        AIEvent.tool_name == "search_catalog",
        AIEvent.success.is_(True),
        AIEvent.created_at >= cutoff,
    ]

    if last_checkout is not None:
        conditions.append(AIEvent.created_at > last_checkout.created_at)

    events = list(
        db.scalars(
            select(AIEvent)
            .where(*conditions)
            .order_by(AIEvent.created_at.desc())
            .limit(20)
        ).all()
    )

    repository = ProductRepository()
    rows = []
    seen_codes = set()
    family_rows = []
    seen_families = set()

    for event in events:
        payload = event.payload_json or {}
        arguments = payload.get("arguments") or {}
        result = payload.get("result") or {}

        if not result.get("ok"):
            continue

        data = result.get("data") or {}
        query = data.get("query") or arguments.get("query") or ""
        service_mode = arguments.get("service_mode")

        families = data.get("families") or []

        if families:
            first_family = families[0]
            first_family_score = float(
                first_family.get("relevance_score") or 0
            )
            second_family_score = (
                float(families[1].get("relevance_score") or 0)
                if len(families) > 1
                else 0.0
            )
            family_name = str(first_family.get("name") or "").strip()

            if (
                family_name
                and family_name not in seen_families
                and first_family_score >= 0.85
                and first_family_score - second_family_score >= 0.20
            ):
                option_rows = []

                for option in first_family.get("options") or []:
                    code = option.get("external_code")

                    if not code:
                        continue

                    product = repository.get_by_external_code(
                        db,
                        store_id=store_id,
                        external_code=code,
                    )

                    if product is None or not product.active:
                        continue

                    if (
                        service_mode == "DELIVERY"
                        and not product.available_for_delivery
                    ):
                        continue

                    if (
                        service_mode == "TAKEOUT"
                        and not product.available_for_takeout
                    ):
                        continue

                    option_rows.append(
                        f"codigo={product.external_code}; "
                        f"nome={product.name}; "
                        f"preco_atual={product.price}"
                    )

                if option_rows:
                    family_rows.append(
                        f"familia={family_name}; "
                        f"selecao={first_family.get("selection_name") or "Opção"}; "
                        f"opcoes=[{" | ".join(option_rows)}]"
                    )
                    seen_families.add(family_name)

        products = data.get("products") or []

        if not products:
            continue

        first = products[0]
        first_score = float(first.get("relevance_score") or 0)
        second_score = (
            float(products[1].get("relevance_score") or 0)
            if len(products) > 1
            else 0.0
        )

        first_code = first.get("external_code")
        first_product = (
            repository.get_by_external_code(
                db,
                store_id=store_id,
                external_code=first_code,
            )
            if first_code
            else None
        )

        if first_product is None or not first_product.active:
            continue

        exact_name_match = (
            normalize_text(query)
            == normalize_text(first_product.name)
        )

        # Uma correspondência exata com o nome atual do produto no banco
        # é inequívoca mesmo quando existem variações muito parecidas,
        # como "X SALADA" e "X SALADA BACON".
        #
        # Para buscas não exatas, preservamos a proteção conservadora
        # existente de score mínimo + margem para o segundo resultado.
        if not exact_name_match:
            if first_score < 0.90:
                continue

            if first_score - second_score < 0.20:
                continue

        codes = [first_code]

        for code in codes:
            if not code or code in seen_codes:
                continue

            product = repository.get_by_external_code(
                db,
                store_id=store_id,
                external_code=code,
            )

            if product is None or not product.active:
                continue

            if service_mode == "DELIVERY" and not product.available_for_delivery:
                continue

            if service_mode == "TAKEOUT" and not product.available_for_takeout:
                continue

            rows.append(
                f"codigo={product.external_code}; "
                f"nome={product.name}; "
                f"preco_atual={product.price}; "
                f"consulta={query}"
            )
            seen_codes.add(code)

            if len(rows) >= 6:
                break

        if len(rows) >= 6:
            break

    if not rows and not family_rows:
        return (
            "PRODUTOS RECENTEMENTE VALIDADOS: nenhum produto recente "
            "disponível para reutilização."
        )

    sections = []

    if rows:
        sections.append(
            "PRODUTOS INEQUÍVOCOS: " + " | ".join(rows)
        )

    if family_rows:
        sections.append(
            "FAMÍLIAS E OPÇÕES VENDÁVEIS: " + " | ".join(family_rows)
        )

    return (
        "PRODUTOS RECENTEMENTE VALIDADOS PELO SMARTFOODIA: "
        + " || ".join(sections)
        + ". Estes dados foram revalidados no banco agora. "
        "Para PRODUTO INEQUÍVOCO, reutilize o código somente quando o cliente "
        "estiver se referindo claramente ao mesmo produto já apresentado. "
        "Para FAMÍLIA, nunca escolha uma opção, tamanho, sabor ou volume "
        "automaticamente. Se o cliente mencionar apenas a família, pergunte "
        "qual opção deseja. Se o cliente indicar inequivocamente uma opção "
        "que esteja listada aqui, como 1 litro ou 2 litros, reutilize somente "
        "o código vendável daquela opção e não execute search_catalog apenas "
        "para redescobrir a mesma opção. Nunca use family_external_code. "
        "Para produto novo, dúvida, ambiguidade, alteração não coberta pelas "
        "opções listadas ou adicionais, consulte o catálogo normalmente. "
        "Nunca mostre código PDV ao cliente."
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

        # Mídias como comprovantes PIX permanecem registradas no histórico
        # para auditoria, mas não devem virar contexto textual da Olivia.
        ai_history = [
            message
            for message in history
            if (message.content_type or "TEXT").upper() == "TEXT"
        ]

        checkout_required = _checkout_required_by_customer(
            history=ai_history,
            customer_message=customer_message,
        )

        force_greeting = _should_force_greeting(
            history=ai_history,
            customer_message=customer_message,
        )

        input_items = [
            {
                "role": "user" if message.sender_type == "CUSTOMER" else "assistant",
                "content": message.content,
            }
            for message in ai_history
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
            + "\n\n"
            + _recent_validated_products_context(
                db,
                store_id=store_id,
                conversation_id=conversation_id,
            )
        )
        if extra_instructions:
            instructions += "\n\n" + extra_instructions

        if checkout_required:
            instructions += (
                "\n\nCONTROLE TRANSACIONAL OBRIGATÓRIO: "
                "o cliente acabou de confirmar explicitamente o resumo final "
                "do pedido. Você DEVE executar checkout_cart antes de dizer "
                "que o pedido foi confirmado, antes de informar número de "
                "pedido e antes de agradecer como se a compra estivesse "
                "registrada. O número do pedido só pode vir do resultado "
                "bem-sucedido de checkout_cart. Nunca invente ou estime "
                "display_id."
            )


        blocked_tools = excluded_tools or set()
        available_tools = [
            tool
            for tool in self._provider_tools(registry)
            if tool["name"] not in blocked_tools
        ]

        previous_response_id = None

        pix_checkout_instructions: str | None = None
        pix_checkout_key: str | None = None

        checkout_succeeded_this_reply = False
        checkout_retry_forced = False

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
                        "model": response.model,
                        "usage": response.usage,
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

                        if (
                            call.name == "checkout_cart"
                            and result.ok
                        ):
                            checkout_succeeded_this_reply = True

                        if (
                            call.name == "checkout_cart"
                            and result.ok
                            and isinstance(result.data, dict)
                            and (
                                result.data.get("payment_method") == "PIX"
                                or any(
                                    str(payment.get("method") or "").upper()
                                    == "PIX"
                                    for payment in result.data.get("payments") or []
                                )
                            )
                        ):
                            (
                                pix_checkout_instructions,
                                pix_checkout_key,
                            ) = _pix_payment_instructions(
                                db,
                                store_id=store_id,
                                order_data=result.data,
                            )

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
                if (
                    checkout_required
                    and not checkout_succeeded_this_reply
                ):
                    if (
                        not checkout_retry_forced
                        and round_number
                        < settings.olivia_max_tool_rounds
                    ):
                        checkout_retry_forced = True

                        input_items = [
                            {
                                "role": "user",
                                "content": (
                                    "CONTROLE INTERNO: você tentou responder "
                                    "sem registrar o pedido. Não envie texto "
                                    "ao cliente ainda. Execute checkout_cart "
                                    "agora usando os dados já confirmados. "
                                    "Somente após resultado ok=true você pode "
                                    "informar que o pedido foi confirmado e "
                                    "usar o display_id devolvido pela ferramenta."
                                ),
                            }
                        ]
                        continue

                    final_text = (
                        "Não consegui registrar seu pedido no sistema ainda. "
                        "Ele não foi confirmado. Vou precisar tentar a "
                        "finalização novamente antes de te passar um número "
                        "de pedido."
                    )
                else:
                    final_text = response.text.strip()

                if force_greeting:
                    final_text = _ensure_local_greeting(
                        final_text
                    )

                if (
                    pix_checkout_instructions
                    and pix_checkout_key
                ):
                    final_text = _ensure_pix_payment_instructions(
                        final_text,
                        instructions=pix_checkout_instructions,
                        pix_key=pix_checkout_key,
                    )

                self.conversations.add_message(
                    db,
                    conversation_id=conversation_id,
                    payload=MessageCreate(
                        direction="OUTBOUND",
                        sender_type="OLIVIA",
                        content=final_text,
                    ),
                )

                return final_text

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
