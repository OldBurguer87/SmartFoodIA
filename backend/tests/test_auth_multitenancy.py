from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router as auth_router
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
