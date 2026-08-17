import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.security import verify_password
from app.database.base import Base
from app.services.auth import AuthService
from app.scripts.bootstrap_platform_admin import (
    bootstrap_platform_admin,
)


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


def test_creates_platform_admin(db):
    user = bootstrap_platform_admin(
        db,
        name="Administrador",
        email=" ADMIN@EXAMPLE.COM ",
        password="Senha-Segura-12345",
    )

    assert user.email == "admin@example.com"
    assert user.name == "Administrador"
    assert user.active is True
    assert user.is_platform_admin is True

    assert verify_password(
        "Senha-Segura-12345",
        user.password_hash,
    )


def test_existing_user_requires_explicit_update(db):
    bootstrap_platform_admin(
        db,
        name="Administrador",
        email="admin@example.com",
        password="Senha-Segura-12345",
    )

    with pytest.raises(
        ValueError,
        match="Usuário já existe",
    ):
        bootstrap_platform_admin(
            db,
            name="Outro Nome",
            email="admin@example.com",
            password="Outra-Senha-12345",
        )


def test_can_update_existing_admin_explicitly(db):
    original = bootstrap_platform_admin(
        db,
        name="Administrador",
        email="admin@example.com",
        password="Senha-Segura-12345",
    )

    updated = bootstrap_platform_admin(
        db,
        name="Administrador Atualizado",
        email="admin@example.com",
        password="Nova-Senha-Segura-12345",
        update_existing=True,
    )

    assert updated.id == original.id
    assert updated.name == "Administrador Atualizado"
    assert updated.active is True
    assert updated.is_platform_admin is True

    assert verify_password(
        "Nova-Senha-Segura-12345",
        updated.password_hash,
    )


def test_rejects_short_password(db):
    with pytest.raises(
        ValueError,
        match="12 caracteres",
    ):
        bootstrap_platform_admin(
            db,
            name="Administrador",
            email="admin@example.com",
            password="curta",
        )


def test_created_admin_gets_platform_access(db):
    user = bootstrap_platform_admin(
        db,
        name="Administrador",
        email="admin@example.com",
        password="Senha-Segura-12345",
    )

    companies = AuthService().user_companies(
        db,
        user,
    )

    assert companies == []


def test_bootstrapped_admin_can_login(db):
    user = bootstrap_platform_admin(
        db,
        name="Administrador",
        email="admin@example.com",
        password="Senha-Segura-12345",
    )

    authenticated, raw_token = AuthService().login(
        db,
        email="admin@example.com",
        password="Senha-Segura-12345",
    )

    assert authenticated.user.id == user.id
    assert authenticated.user.is_platform_admin is True
    assert raw_token
    assert len(raw_token) > 20
