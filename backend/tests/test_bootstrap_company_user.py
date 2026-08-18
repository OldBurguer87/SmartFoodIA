import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.security import (
    hash_password,
    verify_password,
)
from app.database.base import Base
from app.models.auth import CompanyUser, User
from app.models.catalog import Company, Store
from app.scripts.bootstrap_company_user import (
    bootstrap_company_user,
)
from app.services.auth import AuthService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    Session = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with Session() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def companies(db):
    company_a = Company(
        name="Empresa A",
        active=True,
    )

    company_b = Company(
        name="Empresa B",
        active=True,
    )

    db.add_all([
        company_a,
        company_b,
    ])
    db.flush()

    store_a = Store(
        company_id=company_a.id,
        name="Loja A",
        slug="loja-a-bootstrap",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
        active=True,
    )

    store_b = Store(
        company_id=company_b.id,
        name="Loja B",
        slug="loja-b-bootstrap",
        city="Coari",
        state="AM",
        timezone="America/Manaus",
        active=True,
    )

    db.add_all([
        store_a,
        store_b,
    ])
    db.commit()

    return {
        "company_a": company_a,
        "company_b": company_b,
        "store_a": store_a,
        "store_b": store_b,
    }


def test_creates_company_owner(db, companies):
    user, membership = bootstrap_company_user(
        db,
        company_id=companies["company_a"].id,
        name=" Gestor da Empresa ",
        email=" GESTOR@EXAMPLE.COM ",
        password="Senha-Segura-12345",
        role="owner",
    )

    assert user.name == "Gestor da Empresa"
    assert user.email == "gestor@example.com"
    assert user.active is True
    assert user.is_platform_admin is False

    assert verify_password(
        "Senha-Segura-12345",
        user.password_hash,
    )

    assert membership.company_id == (
        companies["company_a"].id
    )
    assert membership.user_id == user.id
    assert membership.role == "OWNER"
    assert membership.active is True


def test_user_can_login_and_only_access_own_company(
    db,
    companies,
):
    user, _ = bootstrap_company_user(
        db,
        company_id=companies["company_a"].id,
        name="Gestor",
        email="gestor@example.com",
        password="Senha-Segura-12345",
        role="MANAGER",
    )

    authenticated, raw_token = AuthService().login(
        db,
        email="gestor@example.com",
        password="Senha-Segura-12345",
    )

    assert authenticated.user.id == user.id
    assert raw_token

    assert AuthService().can_access_store(
        db,
        user,
        companies["store_a"].id,
    ) is True

    assert AuthService().can_access_store(
        db,
        user,
        companies["store_b"].id,
    ) is False

    visible = AuthService().user_companies(
        db,
        user,
    )

    assert len(visible) == 1
    assert visible[0]["id"] == str(
        companies["company_a"].id
    )


def test_existing_user_requires_explicit_update(
    db,
    companies,
):
    bootstrap_company_user(
        db,
        company_id=companies["company_a"].id,
        name="Gestor",
        email="gestor@example.com",
        password="Senha-Segura-12345",
    )

    with pytest.raises(
        ValueError,
        match="Usuário já existe",
    ):
        bootstrap_company_user(
            db,
            company_id=companies["company_a"].id,
            name="Outro Nome",
            email="gestor@example.com",
            password="Outra-Senha-12345",
        )


def test_explicit_update_changes_role_and_password(
    db,
    companies,
):
    original, original_membership = (
        bootstrap_company_user(
            db,
            company_id=companies["company_a"].id,
            name="Gestor",
            email="gestor@example.com",
            password="Senha-Segura-12345",
            role="VIEWER",
        )
    )

    updated, membership = bootstrap_company_user(
        db,
        company_id=companies["company_a"].id,
        name="Gestor Atualizado",
        email="gestor@example.com",
        password="Nova-Senha-Segura-12345",
        role="ADMIN",
        update_existing=True,
    )

    assert updated.id == original.id
    assert membership.id == original_membership.id
    assert updated.name == "Gestor Atualizado"
    assert membership.role == "ADMIN"
    assert membership.active is True

    assert verify_password(
        "Nova-Senha-Segura-12345",
        updated.password_hash,
    )


def test_existing_platform_admin_is_not_demoted(
    db,
    companies,
):
    admin = User(
        name="Administrador",
        email="admin@example.com",
        password_hash=hash_password(
            "Senha-Antiga-Segura-12345"
        ),
        active=True,
        is_platform_admin=True,
    )

    db.add(admin)
    db.commit()

    updated, membership = bootstrap_company_user(
        db,
        company_id=companies["company_a"].id,
        name="Administrador",
        email="admin@example.com",
        password="Nova-Senha-Segura-12345",
        role="OWNER",
        update_existing=True,
    )

    assert updated.id == admin.id
    assert updated.is_platform_admin is True
    assert membership.role == "OWNER"


def test_rejects_invalid_role(db, companies):
    with pytest.raises(
        ValueError,
        match="Função inválida",
    ):
        bootstrap_company_user(
            db,
            company_id=companies["company_a"].id,
            name="Gestor",
            email="gestor@example.com",
            password="Senha-Segura-12345",
            role="SUPERADMIN",
        )


def test_rejects_inactive_company_without_creating_user(
    db,
):
    company = Company(
        name="Empresa Desativada",
        active=False,
    )

    db.add(company)
    db.commit()

    with pytest.raises(
        ValueError,
        match="Empresa está desativada",
    ):
        bootstrap_company_user(
            db,
            company_id=company.id,
            name="Gestor",
            email="gestor@example.com",
            password="Senha-Segura-12345",
        )

    user = db.scalar(
        select(User).where(
            User.email == "gestor@example.com",
        )
    )

    assert user is None


def test_rejects_short_password(db, companies):
    with pytest.raises(
        ValueError,
        match="12 caracteres",
    ):
        bootstrap_company_user(
            db,
            company_id=companies["company_a"].id,
            name="Gestor",
            email="gestor@example.com",
            password="curta",
        )
