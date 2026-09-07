from decimal import Decimal
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.base import ProviderResponse, ProviderToolCall
from app.database.base import Base
from app.models.catalog import Company, Product, Store
from app.models.conversation import AIEvent, Message
from app.schemas.conversation import ConversationCreate
from app.services.conversation import ConversationService

class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def respond(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

def setup_context():
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
    db.add(Product(
        store_id=store.id,
        external_code="235",
        name="Old Monster",
        description="Hambúrguer artesanal",
        price=Decimal("60.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    ))
    db.commit()
    conversation = ConversationService().get_or_create(
        db,
        ConversationCreate(
            store_id=store.id,
            channel="WHATSAPP",
            external_conversation_id="wa-test",
        ),
    )
    return db, store, conversation

def test_orchestrator_executes_tool_then_returns_text():
    db, store, conversation = setup_context()
    provider = FakeProvider([
        ProviderResponse(
            response_id="resp-1",
            tool_calls=[ProviderToolCall(
                call_id="call-1",
                name="search_catalog",
                arguments={"query": "monster", "service_mode": "DELIVERY", "limit": 10},
            )],
        ),
        ProviderResponse(response_id="resp-2", text="Temos o Old Monster por R$ 60,00."),
    ])
    reply = OliviaOrchestrator(provider).reply(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        customer_message="Tem Monster?",
        customer_phone="97999999999",
    )
    assert reply.startswith(
        ("Bom dia!", "Boa tarde!", "Boa noite!")
    )
    assert reply.endswith(
        "Temos o Old Monster por R$ 60,00."
    )
    assert provider.calls[1]["previous_response_id"] == "resp-1"
    assert provider.calls[1]["input_items"][0]["type"] == "function_call_output"
    messages = list(db.scalars(select(Message).where(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at)))
    assert messages[0].sender_type == "CUSTOMER"
    assert messages[-1].sender_type == "OLIVIA"
    events = list(db.scalars(select(AIEvent).where(
        AIEvent.conversation_id == conversation.id
    )))
    assert any(event.event_type == "TOOL_EXECUTION" for event in events)

def test_orchestrator_returns_direct_response_without_tool():
    db, store, conversation = setup_context()
    provider = FakeProvider([
        ProviderResponse(response_id="resp-1", text="Olá! Como posso ajudar?")
    ])
    reply = OliviaOrchestrator(provider).reply(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        customer_message="Oi",
    )
    assert reply.startswith(
        ("Bom dia!", "Boa tarde!", "Boa noite!")
    )
    assert reply.endswith(
        "Olá! Como posso ajudar?"
    )


def test_orchestrator_excludes_media_messages_from_ai_history():
    db, store, conversation = setup_context()

    db.add(
        Message(
            conversation_id=conversation.id,
            direction="INBOUND",
            sender_type="CUSTOMER",
            content_type="IMAGE",
            content="[Comprovante PIX recebido]",
        )
    )
    db.commit()

    provider = FakeProvider([
        ProviderResponse(
            response_id="resp-media-filter",
            text="Olá! Como posso ajudar?",
        )
    ])

    OliviaOrchestrator(provider).reply(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        customer_message="Oi",
    )

    input_items = provider.calls[0]["input_items"]

    assert any(
        item["role"] == "user" and item["content"] == "Oi"
        for item in input_items
    )

    assert all(
        item["content"] != "[Comprovante PIX recebido]"
        for item in input_items
    )

def test_orchestrator_includes_current_operational_state_in_instructions():
    from app.models.cart import Cart, CartItem
    from app.models.customer import Customer, CustomerAddress

    db, store, conversation = setup_context()

    customer = Customer(
        store_id=store.id,
        name="Eliomara",
        phone="97999999999",
        active=True,
    )
    db.add(customer)
    db.flush()

    address = CustomerAddress(
        customer_id=customer.id,
        label="Principal",
        street="Estrada Coari Mamiá",
        number="475",
        neighborhood="União",
        city="Coari",
        state="AM",
        reference="FQueiroz",
        is_default=True,
        active=True,
    )
    db.add(address)

    product = db.scalar(
        select(Product).where(
            Product.store_id == store.id,
            Product.external_code == "235",
        )
    )
    assert product is not None

    cart = Cart(
        store_id=store.id,
        customer_id=customer.id,
        status="OPEN",
        service_mode="DELIVERY",
    )
    db.add(cart)
    db.flush()

    cart_item = CartItem(
        cart_id=cart.id,
        product_id=product.id,
        product_external_code=product.external_code,
        product_name=product.name,
        quantity=2,
        unit_price=product.price,
        observations=None,
    )
    db.add(cart_item)
    db.commit()

    provider = FakeProvider([
        ProviderResponse(
            response_id="resp-operational-context",
            text="Certo, podemos continuar.",
        )
    ])

    OliviaOrchestrator(provider).reply(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
        customer_message="Pode continuar",
        customer_phone=customer.phone,
    )

    instructions = provider.calls[0]["instructions"]

    assert "ESTADO OPERACIONAL ATUAL:" in instructions
    assert "sem executar search_catalog apenas para redescobrir" in instructions
    assert "Consulte o catálogo novamente se o cliente mencionar produto novo" in instructions
    assert "EXCETO quando o produto e o preço já estiverem presentes" in instructions
    assert f"customer_id={customer.id}" in instructions
    assert f"address_id={address.id}" in instructions
    assert f"cart_id={cart.id}" in instructions
    assert "modalidade=DELIVERY" in instructions
    assert "subtotal=120.00" in instructions
    assert f"item_id={cart_item.id}" in instructions
    assert "codigo=235" in instructions
    assert "2x Old Monster" in instructions

def test_recent_validated_products_context_keeps_only_unambiguous_product():
    from app.ai.orchestrator import _recent_validated_products_context

    db, store, conversation = setup_context()

    second_product = Product(
        store_id=store.id,
        external_code="236",
        name="Old Monster Especial",
        description="Outro produto parecido",
        price=Decimal("65.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add(second_product)
    db.commit()

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "monster",
                    "service_mode": "DELIVERY",
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "monster",
                        "families": [],
                        "products": [
                            {
                                "external_code": "235",
                                "relevance_score": 0.95,
                            },
                            {
                                "external_code": "236",
                                "relevance_score": 0.40,
                            },
                        ],
                    },
                },
            },
        )
    )

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "especial",
                    "service_mode": "DELIVERY",
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "especial",
                        "families": [],
                        "products": [
                            {
                                "external_code": "236",
                                "relevance_score": 0.92,
                            },
                            {
                                "external_code": "235",
                                "relevance_score": 0.80,
                            },
                        ],
                    },
                },
            },
        )
    )
    db.commit()

    context = _recent_validated_products_context(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
    )

    assert "PRODUTOS RECENTEMENTE VALIDADOS PELO SMARTFOODIA" in context
    assert "codigo=235" in context
    assert "nome=Old Monster" in context
    assert "preco_atual=60.00" in context
    assert "codigo=236" not in context

def test_recent_validated_family_keeps_options_without_auto_selecting():
    from app.ai.orchestrator import _recent_validated_products_context

    db, store, conversation = setup_context()

    products = [
        Product(
            store_id=store.id,
            external_code="112",
            name="Refrigerante Baré Lata",
            price=Decimal("5.00"),
            active=True,
            available_for_delivery=True,
            available_for_takeout=True,
        ),
        Product(
            store_id=store.id,
            external_code="111",
            name="Refrigerante Baré 1 lt",
            price=Decimal("8.00"),
            active=True,
            available_for_delivery=True,
            available_for_takeout=True,
        ),
        Product(
            store_id=store.id,
            external_code="110",
            name="Refrigerante Baré 2 litros",
            price=Decimal("10.00"),
            active=True,
            available_for_delivery=True,
            available_for_takeout=True,
        ),
    ]
    db.add_all(products)
    db.commit()

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "Baré",
                    "service_mode": "DELIVERY",
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "Baré",
                        "families": [
                            {
                                "family_external_code": "P85",
                                "name": "Refrigerante Baré",
                                "selection_name": "Tamanho",
                                "relevance_score": 0.90,
                                "options": [
                                    {"external_code": "112"},
                                    {"external_code": "111"},
                                    {"external_code": "110"},
                                ],
                            }
                        ],
                        "products": [],
                    },
                },
            },
        )
    )
    db.commit()

    context = _recent_validated_products_context(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
    )

    assert "familia=Refrigerante Baré" in context
    assert "selecao=Tamanho" in context
    assert "codigo=112" in context
    assert "codigo=111" in context
    assert "nome=Refrigerante Baré 1 lt" in context
    assert "preco_atual=8.00" in context
    assert "codigo=110" in context
    assert "P85" not in context
    assert "nunca escolha uma opção" in context
    assert "Nunca use family_external_code" in context


def test_recent_validated_products_reuses_exact_name_even_with_close_variant():
    from app.ai.orchestrator import _recent_validated_products_context

    db, store, conversation = setup_context()

    exact_product = Product(
        store_id=store.id,
        external_code="17",
        name="X SALADA",
        description="X Salada tradicional",
        price=Decimal("10.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    close_variant = Product(
        store_id=store.id,
        external_code="20",
        name="X SALADA BACON",
        description="X Salada com bacon",
        price=Decimal("12.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add_all([exact_product, close_variant])
    db.commit()

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "x salada",
                    "service_mode": None,
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "x salada",
                        "families": [],
                        "products": [
                            {
                                "external_code": "17",
                                "name": "X SALADA",
                                "relevance_score": 1.0,
                            },
                            {
                                "external_code": "20",
                                "name": "X SALADA BACON",
                                "relevance_score": 0.95,
                            },
                        ],
                    },
                },
            },
        )
    )
    db.commit()

    context = _recent_validated_products_context(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
    )

    assert "PRODUTOS RECENTEMENTE VALIDADOS PELO SMARTFOODIA" in context
    assert "codigo=17" in context
    assert "nome=X SALADA" in context
    assert "preco_atual=10.00" in context


def test_recent_validated_products_reuses_old_jr_exact_name_with_trio_close():
    from app.ai.orchestrator import _recent_validated_products_context

    db, store, conversation = setup_context()

    exact_product = Product(
        store_id=store.id,
        external_code="114",
        name="Old Jr.",
        description="Hambúrguer Old Jr",
        price=Decimal("15.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    close_variant = Product(
        store_id=store.id,
        external_code="135",
        name="Trio Old Jr.",
        description="Combo com Old Jr",
        price=Decimal("25.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add_all([exact_product, close_variant])
    db.commit()

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "Old Jr",
                    "service_mode": None,
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "Old Jr",
                        "families": [],
                        "products": [
                            {
                                "external_code": "114",
                                "name": "Old Jr.",
                                "relevance_score": 1.0,
                            },
                            {
                                "external_code": "135",
                                "name": "Trio Old Jr.",
                                "relevance_score": 0.90,
                            },
                        ],
                    },
                },
            },
        )
    )
    db.commit()

    context = _recent_validated_products_context(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
    )

    assert "codigo=114" in context
    assert "nome=Old Jr." in context
    assert "preco_atual=15.00" in context


def test_recent_validated_products_keeps_margin_rule_for_non_exact_query():
    from app.ai.orchestrator import _recent_validated_products_context

    db, store, conversation = setup_context()

    first_product = Product(
        store_id=store.id,
        external_code="17",
        name="X SALADA",
        description="X Salada tradicional",
        price=Decimal("10.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    second_product = Product(
        store_id=store.id,
        external_code="20",
        name="X SALADA BACON",
        description="X Salada com bacon",
        price=Decimal("12.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=True,
    )
    db.add_all([first_product, second_product])
    db.commit()

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "salada",
                    "service_mode": None,
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "salada",
                        "families": [],
                        "products": [
                            {
                                "external_code": "17",
                                "name": "X SALADA",
                                "relevance_score": 0.90,
                            },
                            {
                                "external_code": "20",
                                "name": "X SALADA BACON",
                                "relevance_score": 0.85,
                            },
                        ],
                    },
                },
            },
        )
    )
    db.commit()

    context = _recent_validated_products_context(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
    )

    assert "nenhum produto recente disponível para reutilização" in context
    assert "codigo=17" not in context


def test_recent_validated_exact_product_respects_takeout_availability():
    from app.ai.orchestrator import _recent_validated_products_context

    db, store, conversation = setup_context()

    product = Product(
        store_id=store.id,
        external_code="17",
        name="X SALADA",
        description="X Salada tradicional",
        price=Decimal("10.00"),
        active=True,
        available_for_delivery=True,
        available_for_takeout=False,
    )
    db.add(product)
    db.commit()

    db.add(
        AIEvent(
            store_id=store.id,
            conversation_id=conversation.id,
            event_type="TOOL_EXECUTION",
            tool_name="search_catalog",
            success=True,
            payload_json={
                "arguments": {
                    "query": "x salada",
                    "service_mode": "TAKEOUT",
                    "limit": 10,
                },
                "result": {
                    "ok": True,
                    "data": {
                        "query": "x salada",
                        "families": [],
                        "products": [
                            {
                                "external_code": "17",
                                "name": "X SALADA",
                                "relevance_score": 1.0,
                            }
                        ],
                    },
                },
            },
        )
    )
    db.commit()

    context = _recent_validated_products_context(
        db,
        store_id=store.id,
        conversation_id=conversation.id,
    )

    assert "nenhum produto recente disponível para reutilização" in context
    assert "codigo=17" not in context
