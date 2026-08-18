from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router as auth_router
from app.api.analytics import router as analytics_router
from app.api.carts import router as carts_router
from app.api.catalog import router as catalog_router
from app.api.modifiers import router as modifiers_router
from app.api.customers import router as customers_router
from app.api.orders import router as orders_router
from app.api.commercial_rules import router as commercial_router
from app.api.customer_operations import router as customer_operations_router
from app.api.catalog_operations import router as catalog_operations_router
from app.api.menu_documents import router as menu_documents_router
from app.api.operations import router as operations_router
from app.api.support_operations import router as support_operations_router
from app.api.operational_dashboard import router as operational_dashboard_router
from app.core.config import settings
from app.core.security import hash_password, hash_session_token
from app.database.base import Base
from app.database.session import get_db
from app.models.auth import AuthSession, CompanyUser, User
from app.models.catalog import Company, Store
from app.models.cart import Cart
from app.models.order import Order
from app.models.customer import Customer
from app.models.conversation import (
    Conversation,
    HumanTicket,
    KnowledgeGap,
)


@pytest.fixture()
def environment():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(analytics_router)
    app.include_router(carts_router)
    app.include_router(catalog_router)
    app.include_router(modifiers_router)
    app.include_router(customers_router)
    app.include_router(orders_router)
    app.include_router(commercial_router)
    app.include_router(customer_operations_router)
    app.include_router(catalog_operations_router)
    app.include_router(menu_documents_router)
    app.include_router(operations_router)
    app.include_router(support_operations_router)
    app.include_router(operational_dashboard_router)
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(
        app,
        base_url="https://testserver",
    )

    db: Session = SessionLocal()

    company_a = Company(
        name="Empresa A",
    )
    company_b = Company(
        name="Empresa B",
    )

    db.add_all([company_a, company_b])
    db.flush()

    store_a = Store(
        company_id=company_a.id,
        name="Loja A",
        slug="loja-a",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )

    store_b = Store(
        company_id=company_b.id,
        name="Loja B",
        slug="loja-b",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
    )

    db.add_all([store_a, store_b])
    db.flush()

    customer_a = Customer(
        store_id=store_a.id,
        name="Cliente Empresa A",
        phone="5597981111111",
        active=True,
    )

    customer_b = Customer(
        store_id=store_b.id,
        name="Cliente Empresa B",
        phone="5597982222222",
        active=True,
    )

    db.add_all([customer_a, customer_b])
    db.flush()

    cart_a = Cart(
        store_id=store_a.id,
        customer_id=customer_a.id,
        status="OPEN",
        service_mode="DELIVERY",
    )

    cart_b = Cart(
        store_id=store_b.id,
        customer_id=customer_b.id,
        status="OPEN",
        service_mode="DELIVERY",
    )

    db.add_all([cart_a, cart_b])
    db.flush()

    order_a = Order(
        store_id=store_a.id,
        customer_id=customer_a.id,
        cart_id=cart_a.id,
        display_id="000001",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PENDING",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("23.00"),
        customer_name=customer_a.name,
        customer_phone=customer_a.phone,
    )

    order_b = Order(
        store_id=store_b.id,
        customer_id=customer_b.id,
        cart_id=cart_b.id,
        display_id="000001",
        status="READY_FOR_INTEGRATION",
        service_mode="DELIVERY",
        payment_method="PIX",
        payment_type="PENDING",
        subtotal=Decimal("20.00"),
        delivery_fee=Decimal("3.00"),
        discount=Decimal("0.00"),
        total=Decimal("23.00"),
        customer_name=customer_b.name,
        customer_phone=customer_b.phone,
    )

    db.add_all([order_a, order_b])
    db.flush()

    viewer = User(
        name="Viewer A",
        email="viewer@empresa-a.test",
        password_hash=hash_password("Senha-Viewer-123"),
        active=True,
    )

    manager = User(
        name="Manager A",
        email="manager@empresa-a.test",
        password_hash=hash_password("Senha-Manager-123"),
        active=True,
    )

    platform_admin = User(
        name="SmartFoodIA Admin",
        email="admin@smartfoodia.test",
        password_hash=hash_password("Senha-Platform-123"),
        active=True,
        is_platform_admin=True,
    )

    db.add_all(
        [
            viewer,
            manager,
            platform_admin,
        ]
    )
    db.flush()

    conversation_b = Conversation(
        store_id=store_b.id,
        channel="WHATSAPP",
        external_conversation_id="5597999990000",
        status="OPEN",
    )
    db.add(conversation_b)
    db.flush()

    ticket_b = HumanTicket(
        store_id=store_b.id,
        category="TESTE",
        priority="NORMAL",
        reason="Ticket da Empresa B",
        customer_message="Mensagem de teste",
    )

    gap_b = KnowledgeGap(
        store_id=store_b.id,
        question="Pergunta da Empresa B?",
        normalized_question="pergunta da empresa b",
    )

    db.add_all([ticket_b, gap_b])
    db.flush()

    db.add_all(
        [
            CompanyUser(
                company_id=company_a.id,
                user_id=viewer.id,
                role="VIEWER",
                active=True,
            ),
            CompanyUser(
                company_id=company_a.id,
                user_id=manager.id,
                role="MANAGER",
                active=True,
            ),
        ]
    )

    tokens = {
        "viewer": "token-viewer-a",
        "manager": "token-manager-a",
        "platform_admin": "token-platform-admin",
    }

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(hours=12)
    )

    db.add_all(
        [
            AuthSession(
                user_id=viewer.id,
                token_hash=hash_session_token(
                    tokens["viewer"],
                ),
                expires_at=expires_at,
            ),
            AuthSession(
                user_id=manager.id,
                token_hash=hash_session_token(
                    tokens["manager"],
                ),
                expires_at=expires_at,
            ),
            AuthSession(
                user_id=platform_admin.id,
                token_hash=hash_session_token(
                    tokens["platform_admin"],
                ),
                expires_at=expires_at,
            ),
        ]
    )

    db.commit()

    data = {
        "client": client,
        "db": db,
        "store_a": store_a,
        "store_b": store_b,
        "customer_a": customer_a,
        "customer_b": customer_b,
        "cart_a": cart_a,
        "cart_b": cart_b,
        "order_a": order_a,
        "order_b": order_b,
        "viewer": viewer,
        "manager": manager,
        "platform_admin": platform_admin,
        "conversation_b": conversation_b,
        "ticket_b": ticket_b,
        "gap_b": gap_b,
        "tokens": tokens,
    }

    yield data

    db.close()
    engine.dispose()


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Cookie": (
            f"{settings.auth_cookie_name}={token}"
        ),
    }


def rules_url(store: Store) -> str:
    return (
        f"/api/v1/operations/stores/"
        f"{store.id}/commercial-rules"
    )


def test_without_session_returns_401(
    environment,
) -> None:
    response = environment["client"].get(
        rules_url(environment["store_a"]),
    )

    assert response.status_code == 401


def test_viewer_can_read_own_store(
    environment,
) -> None:
    response = environment["client"].get(
        rules_url(environment["store_a"]),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_company_a_cannot_read_company_b(
    environment,
) -> None:
    response = environment["client"].get(
        rules_url(environment["store_b"]),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_viewer_cannot_change_rules(
    environment,
) -> None:
    response = environment["client"].put(
        rules_url(environment["store_a"]),
        json={
            "manual_paused": True,
        },
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_manager_can_change_rules(
    environment,
) -> None:
    response = environment["client"].put(
        rules_url(environment["store_a"]),
        json={
            "manual_paused": True,
            "pause_reason": "Teste automatizado",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["rules"][
        "manual_paused"
    ] is True


def test_platform_admin_can_access_both_companies(
    environment,
) -> None:
    client = environment["client"]

    for store in (
        environment["store_a"],
        environment["store_b"],
    ):
        response = client.get(
            rules_url(store),
            headers=auth_headers(
                environment["tokens"][
                    "platform_admin"
                ],
            ),
        )

        assert response.status_code == 200


def test_real_login_me_and_logout(
    environment,
) -> None:
    client = environment["client"]

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "MANAGER@EMPRESA-A.TEST",
            "password": "Senha-Manager-123",
        },
    )

    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert login.json()["user"]["email"] == (
        "manager@empresa-a.test"
    )

    me = client.get(
        "/api/v1/auth/me",
    )

    assert me.status_code == 200
    assert me.json()["authenticated"] is True

    logout = client.post(
        "/api/v1/auth/logout",
    )

    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False

    after_logout = client.get(
        "/api/v1/auth/me",
    )

    assert after_logout.status_code == 401


def test_wrong_password_is_rejected(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/auth/login",
        json={
            "email": "manager@empresa-a.test",
            "password": "Senha-Incorreta-123",
        },
    )

    assert response.status_code == 401


def dashboard_url(store: Store) -> str:
    return (
        f"/api/v1/operations/stores/"
        f"{store.id}/overview"
    )


def test_platform_dashboard_requires_session(
    environment,
) -> None:
    response = environment["client"].get(
        "/api/v1/operations/overview",
    )

    assert response.status_code == 401


def test_company_user_cannot_access_platform_dashboard(
    environment,
) -> None:
    response = environment["client"].get(
        "/api/v1/operations/overview",
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_platform_admin_can_access_platform_dashboard(
    environment,
) -> None:
    response = environment["client"].get(
        "/api/v1/operations/overview",
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["summary"]["clients_total"] == 2


def test_company_a_cannot_access_company_b_dashboard(
    environment,
) -> None:
    response = environment["client"].get(
        dashboard_url(environment["store_b"]),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_can_access_own_dashboard(
    environment,
) -> None:
    response = environment["client"].get(
        dashboard_url(environment["store_a"]),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_company_a_cannot_access_company_b_catalog(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/catalog"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_can_access_own_catalog(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/catalog"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_company_a_cannot_access_company_b_menu_admin(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/menu-pdf"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_can_access_own_menu_admin(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/menu-pdf"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_company_a_cannot_list_company_b_conversations(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/conversations"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_can_list_own_conversations(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/conversations"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200


def test_company_a_cannot_open_company_b_conversation_by_id(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/conversations/"
            f"{environment['conversation_b'].id}"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_without_session_cannot_access_catalog(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/catalog"
        ),
    )

    assert response.status_code == 401


def test_company_a_cannot_list_company_b_tickets(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/tickets"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_cannot_assign_company_b_ticket_by_id(
    environment,
) -> None:
    response = environment["client"].post(
        (
            "/api/v1/operations/tickets/"
            f"{environment['ticket_b'].id}/assign"
        ),
        json={
            "assigned_to": "Manager Empresa A",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_company_a_cannot_resolve_company_b_ticket_by_id(
    environment,
) -> None:
    response = environment["client"].post(
        (
            "/api/v1/operations/tickets/"
            f"{environment['ticket_b'].id}/resolve"
        ),
        json={
            "resolution": "Tentativa indevida",
            "assigned_to": "Manager Empresa A",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_company_a_cannot_list_company_b_knowledge_gaps(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/knowledge-gaps"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_cannot_resolve_company_b_gap_by_id(
    environment,
) -> None:
    response = environment["client"].post(
        (
            "/api/v1/operations/knowledge-gaps/"
            f"{environment['gap_b'].id}/resolve"
        ),
        json={
            "answer": "Resposta indevida",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_company_a_can_list_own_support_resources(
    environment,
) -> None:
    tickets = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/tickets"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    gaps = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/knowledge-gaps"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert tickets.status_code == 200
    assert tickets.json() == []

    assert gaps.status_code == 200
    assert gaps.json() == []


def test_customer_wallet_requires_session(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/customers"
        ),
    )

    assert response.status_code == 401


def test_company_a_can_list_only_own_customers(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/customers"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.json()["customers"]
    }

    assert str(environment["customer_a"].id) in ids
    assert str(environment["customer_b"].id) not in ids


def test_company_a_cannot_list_company_b_customers(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/customers"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_company_a_can_open_own_customer(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/customers/"
            f"{environment['customer_a'].id}"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(
        environment["customer_a"].id
    )


def test_company_a_cannot_open_company_b_customer(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/customers/"
            f"{environment['customer_b'].id}"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_customer_id_from_other_store_is_not_exposed(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/customers/"
            f"{environment['customer_b'].id}"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 404


def test_manager_can_configure_pix_and_scheduling(
    environment,
) -> None:
    response = environment["client"].put(
        rules_url(environment["store_a"]),
        json={
            "pix_receiver_name": "Empresa A Recebedora",
            "pix_receiver_document": "12345678901",
            "pix_key": "pix@empresa-a.test",
            "pix_receiver_institution": "BANCO TESTE",
            "pix_auto_verify_enabled": True,
            "pix_receipt_max_age_minutes": 480,
            "pix_amount_tolerance": "0.02",
            "allow_scheduled_orders": True,
            "allow_scheduled_when_closed": False,
            "scheduled_min_notice_minutes": 45,
            "scheduled_max_days_ahead": 7,
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 200

    rules = response.json()["rules"]

    assert rules["pix_receiver_name"] == (
        "Empresa A Recebedora"
    )
    assert rules["pix_receiver_document"] == "12345678901"
    assert rules["pix_key"] == "pix@empresa-a.test"
    assert rules["pix_receiver_institution"] == "BANCO TESTE"
    assert rules["pix_auto_verify_enabled"] is True
    assert rules["pix_receipt_max_age_minutes"] == 480
    assert rules["pix_amount_tolerance"] == 0.02

    assert rules["allow_scheduled_orders"] is True
    assert rules["allow_scheduled_when_closed"] is False
    assert rules["scheduled_min_notice_minutes"] == 45
    assert rules["scheduled_max_days_ahead"] == 7


def test_company_a_cannot_change_company_b_pix_or_scheduling(
    environment,
) -> None:
    response = environment["client"].put(
        rules_url(environment["store_b"]),
        json={
            "pix_key": "tentativa@empresa-b.test",
            "allow_scheduled_orders": False,
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403

    check = environment["client"].get(
        rules_url(environment["store_b"]),
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert check.status_code == 200
    rules = check.json()["rules"]

    assert rules["pix_key"] is None
    assert rules["allow_scheduled_orders"] is True


def test_partial_rules_update_preserves_pix_configuration(
    environment,
) -> None:
    client = environment["client"]
    headers = auth_headers(
        environment["tokens"]["manager"],
    )

    first = client.put(
        rules_url(environment["store_a"]),
        json={
            "pix_receiver_name": "Recebedor Original",
            "pix_key": "original@pix.test",
            "pix_auto_verify_enabled": True,
            "scheduled_max_days_ahead": 10,
        },
        headers=headers,
    )

    assert first.status_code == 200

    second = client.put(
        rules_url(environment["store_a"]),
        json={
            "manual_paused": True,
            "pause_reason": "Pausa de teste",
        },
        headers=headers,
    )

    assert second.status_code == 200

    rules = second.json()["rules"]

    assert rules["manual_paused"] is True
    assert rules["pix_receiver_name"] == "Recebedor Original"
    assert rules["pix_key"] == "original@pix.test"
    assert rules["pix_auto_verify_enabled"] is True
    assert rules["scheduled_max_days_ahead"] == 10


def test_invalid_pix_and_scheduling_values_are_rejected(
    environment,
) -> None:
    headers = auth_headers(
        environment["tokens"]["manager"],
    )

    invalid_notice = environment["client"].put(
        rules_url(environment["store_a"]),
        json={
            "scheduled_min_notice_minutes": -1,
        },
        headers=headers,
    )

    assert invalid_notice.status_code == 422

    invalid_days = environment["client"].put(
        rules_url(environment["store_a"]),
        json={
            "scheduled_max_days_ahead": 366,
        },
        headers=headers,
    )

    assert invalid_days.status_code == 422

    invalid_tolerance = environment["client"].put(
        rules_url(environment["store_a"]),
        json={
            "pix_amount_tolerance": -0.01,
        },
        headers=headers,
    )

    assert invalid_tolerance.status_code == 422


def test_cart_without_session_returns_401(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/carts/{environment['cart_a'].id}",
    )

    assert response.status_code == 401


def test_viewer_can_read_cart_from_own_company(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/carts/{environment['cart_a'].id}",
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_company_a_cannot_read_company_b_cart(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/carts/{environment['cart_b'].id}",
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_viewer_cannot_write_cart(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/carts",
        json={
            "store_id": str(environment["store_a"].id),
            "customer_id": str(
                environment["customer_a"].id
            ),
            "service_mode": "DELIVERY",
        },
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_manager_can_write_cart_from_own_company(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/carts",
        json={
            "store_id": str(environment["store_a"].id),
            "customer_id": str(
                environment["customer_a"].id
            ),
            "service_mode": "DELIVERY",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_manager_cannot_write_company_b_cart(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/carts",
        json={
            "store_id": str(environment["store_b"].id),
            "customer_id": str(
                environment["customer_b"].id
            ),
            "service_mode": "DELIVERY",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_platform_admin_can_read_company_b_cart(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/carts/{environment['cart_b'].id}",
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_b"].id
    )


def test_order_without_session_returns_401(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/orders/{environment['order_a'].id}",
    )

    assert response.status_code == 401


def test_viewer_can_read_order_from_own_company(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/orders/{environment['order_a'].id}",
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(
        environment["order_a"].id
    )


def test_company_a_cannot_read_company_b_order(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/orders/{environment['order_b'].id}",
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_viewer_cannot_checkout_own_company_cart(
    environment,
) -> None:
    response = environment["client"].post(
        f"/api/v1/orders/checkout/{environment['cart_a'].id}",
        json={
            "payment_method": "PIX",
        },
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_manager_can_checkout_own_company_cart(
    environment,
) -> None:
    response = environment["client"].post(
        f"/api/v1/orders/checkout/{environment['cart_a'].id}",
        json={
            "payment_method": "PIX",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(
        environment["order_a"].id
    )


def test_manager_cannot_checkout_company_b_cart(
    environment,
) -> None:
    response = environment["client"].post(
        f"/api/v1/orders/checkout/{environment['cart_b'].id}",
        json={
            "payment_method": "PIX",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_platform_admin_can_read_company_b_order(
    environment,
) -> None:
    response = environment["client"].get(
        f"/api/v1/orders/{environment['order_b'].id}",
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(
        environment["order_b"].id
    )


def test_customer_without_session_returns_401(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/customers/find-or-create",
        json={
            "store_id": str(environment["store_a"].id),
            "name": "Cliente Novo",
            "phone": "5597983333333",
        },
    )

    assert response.status_code == 401


def test_viewer_cannot_create_customer(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/customers/find-or-create",
        json={
            "store_id": str(environment["store_a"].id),
            "name": "Cliente Viewer",
            "phone": "5597983333334",
        },
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_manager_can_create_customer_in_own_company(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/customers/find-or-create",
        json={
            "store_id": str(environment["store_a"].id),
            "name": "Cliente Manager",
            "phone": "5597983333335",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )


def test_manager_cannot_create_customer_in_company_b(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/customers/find-or-create",
        json={
            "store_id": str(environment["store_b"].id),
            "name": "Cliente Empresa B",
            "phone": "5597983333336",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_manager_can_add_address_to_own_customer(
    environment,
) -> None:
    response = environment["client"].post(
        (
            "/api/v1/customers/"
            f"{environment['customer_a'].id}/addresses"
        ),
        json={
            "street": "Rua Empresa A",
            "number": "100",
            "neighborhood": "Centro",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 201
    assert response.json()["customer_id"] == str(
        environment["customer_a"].id
    )


def test_manager_cannot_add_address_to_company_b_customer(
    environment,
) -> None:
    response = environment["client"].post(
        (
            "/api/v1/customers/"
            f"{environment['customer_b'].id}/addresses"
        ),
        json={
            "street": "Rua Indevida",
            "number": "999",
            "neighborhood": "Centro",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_platform_admin_can_add_address_to_company_b_customer(
    environment,
) -> None:
    response = environment["client"].post(
        (
            "/api/v1/customers/"
            f"{environment['customer_b'].id}/addresses"
        ),
        json={
            "street": "Rua Empresa B",
            "number": "200",
            "neighborhood": "Centro",
        },
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert response.status_code == 201
    assert response.json()["customer_id"] == str(
        environment["customer_b"].id
    )


def test_product_create_without_session_returns_401(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/products",
        json={
            "store_id": str(environment["store_a"].id),
            "external_code": "TEST-SEM-SESSAO",
            "name": "Produto Sem Sessao",
            "price": "10.00",
        },
    )

    assert response.status_code == 401


def test_viewer_cannot_create_product(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/products",
        json={
            "store_id": str(environment["store_a"].id),
            "external_code": "TEST-VIEWER",
            "name": "Produto Viewer",
            "price": "10.00",
        },
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_manager_can_create_product_in_own_company(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/products",
        json={
            "store_id": str(environment["store_a"].id),
            "external_code": "TEST-MANAGER-A",
            "name": "Produto Empresa A",
            "price": "12.50",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 201
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )
    assert response.json()["external_code"] == "TEST-MANAGER-A"


def test_manager_cannot_create_product_in_company_b(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/products",
        json={
            "store_id": str(environment["store_b"].id),
            "external_code": "TEST-INDEVIDO-B",
            "name": "Produto Indevido",
            "price": "15.00",
        },
        headers=auth_headers(
            environment["tokens"]["manager"],
        ),
    )

    assert response.status_code == 403


def test_platform_admin_can_create_product_in_company_b(
    environment,
) -> None:
    response = environment["client"].post(
        "/api/v1/products",
        json={
            "store_id": str(environment["store_b"].id),
            "external_code": "TEST-ADMIN-B",
            "name": "Produto Empresa B",
            "price": "20.00",
        },
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert response.status_code == 201
    assert response.json()["store_id"] == str(
        environment["store_b"].id
    )


def test_catalog_reads_remain_public(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_a"].id)

    response = client.get(
        "/api/v1/products",
        params={
            "store_id": store_id,
        },
    )
    assert response.status_code == 200

    response = client.get(
        "/api/v1/products/search",
        params={
            "store_id": store_id,
            "q": "xx",
        },
    )
    assert response.status_code == 200

    response = client.get(
        "/api/v1/products/NAO-EXISTE",
        params={
            "store_id": store_id,
        },
    )
    assert response.status_code == 404


def test_modifier_writes_without_session_return_401(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_a"].id)

    group_response = client.post(
        "/api/v1/catalog/modifier-groups",
        json={
            "store_id": store_id,
            "name": "Grupo Sem Sessao",
        },
    )

    modifier_response = client.post(
        "/api/v1/catalog/modifiers",
        json={
            "store_id": store_id,
            "external_code": "MOD-SEM-SESSAO",
            "name": "Adicional Sem Sessao",
            "price": "2.00",
        },
    )

    assert group_response.status_code == 401
    assert modifier_response.status_code == 401


def test_viewer_cannot_create_modifiers(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_a"].id)
    headers = auth_headers(
        environment["tokens"]["viewer"],
    )

    group_response = client.post(
        "/api/v1/catalog/modifier-groups",
        json={
            "store_id": store_id,
            "name": "Grupo Viewer",
        },
        headers=headers,
    )

    modifier_response = client.post(
        "/api/v1/catalog/modifiers",
        json={
            "store_id": store_id,
            "external_code": "MOD-VIEWER",
            "name": "Adicional Viewer",
            "price": "2.00",
        },
        headers=headers,
    )

    assert group_response.status_code == 403
    assert modifier_response.status_code == 403


def test_manager_can_create_modifiers_in_own_company(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_a"].id)
    headers = auth_headers(
        environment["tokens"]["manager"],
    )

    group_response = client.post(
        "/api/v1/catalog/modifier-groups",
        json={
            "store_id": store_id,
            "name": "Adicionais Empresa A",
        },
        headers=headers,
    )

    modifier_response = client.post(
        "/api/v1/catalog/modifiers",
        json={
            "store_id": store_id,
            "external_code": "MOD-A",
            "name": "Queijo Extra A",
            "price": "3.00",
        },
        headers=headers,
    )

    assert group_response.status_code == 201
    assert modifier_response.status_code == 201

    assert group_response.json()["store_id"] == store_id
    assert modifier_response.json()["store_id"] == store_id


def test_manager_cannot_create_modifiers_in_company_b(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_b"].id)
    headers = auth_headers(
        environment["tokens"]["manager"],
    )

    group_response = client.post(
        "/api/v1/catalog/modifier-groups",
        json={
            "store_id": store_id,
            "name": "Grupo Indevido B",
        },
        headers=headers,
    )

    modifier_response = client.post(
        "/api/v1/catalog/modifiers",
        json={
            "store_id": store_id,
            "external_code": "MOD-INDEVIDO-B",
            "name": "Adicional Indevido B",
            "price": "4.00",
        },
        headers=headers,
    )

    assert group_response.status_code == 403
    assert modifier_response.status_code == 403


def test_platform_admin_can_create_modifiers_in_company_b(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_b"].id)
    headers = auth_headers(
        environment["tokens"]["platform_admin"],
    )

    group_response = client.post(
        "/api/v1/catalog/modifier-groups",
        json={
            "store_id": store_id,
            "name": "Adicionais Empresa B",
        },
        headers=headers,
    )

    modifier_response = client.post(
        "/api/v1/catalog/modifiers",
        json={
            "store_id": store_id,
            "external_code": "MOD-B",
            "name": "Queijo Extra B",
            "price": "5.00",
        },
        headers=headers,
    )

    assert group_response.status_code == 201
    assert modifier_response.status_code == 201


def test_modifier_reads_remain_public(
    environment,
) -> None:
    client = environment["client"]
    store_id = str(environment["store_a"].id)

    groups_response = client.get(
        "/api/v1/catalog/modifier-groups",
        params={
            "store_id": store_id,
        },
    )

    modifiers_response = client.get(
        "/api/v1/catalog/modifiers",
        params={
            "store_id": store_id,
        },
    )

    assert groups_response.status_code == 200
    assert modifiers_response.status_code == 200


def test_store_analytics_without_session_returns_401(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/analytics"
        ),
    )

    assert response.status_code == 401


def test_viewer_can_read_own_store_analytics(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_a'].id}/analytics"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_a"].id
    )
    assert response.json()["summary"]["orders_total"] == 1
    assert response.json()["summary"]["revenue"] == 23.0


def test_company_a_cannot_read_company_b_analytics(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/analytics"
        ),
        headers=auth_headers(
            environment["tokens"]["viewer"],
        ),
    )

    assert response.status_code == 403


def test_platform_admin_can_read_company_b_analytics(
    environment,
) -> None:
    response = environment["client"].get(
        (
            "/api/v1/operations/stores/"
            f"{environment['store_b'].id}/analytics"
        ),
        headers=auth_headers(
            environment["tokens"]["platform_admin"],
        ),
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == str(
        environment["store_b"].id
    )
    assert response.json()["summary"]["orders_total"] == 1
