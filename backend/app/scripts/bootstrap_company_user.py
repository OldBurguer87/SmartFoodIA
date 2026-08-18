from __future__ import annotations

import argparse
import getpass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    normalize_email,
)
from app.database.session import SessionLocal
from app.models.auth import CompanyUser, User
from app.models.catalog import Company


ALLOWED_ROLES = {
    "OWNER",
    "ADMIN",
    "MANAGER",
    "VIEWER",
}


def bootstrap_company_user(
    db: Session,
    *,
    company_id: UUID,
    name: str,
    email: str,
    password: str,
    role: str = "OWNER",
    update_existing: bool = False,
) -> tuple[User, CompanyUser]:
    clean_name = name.strip()
    normalized_email = normalize_email(email)
    normalized_role = role.strip().upper()

    if not clean_name:
        raise ValueError("Nome é obrigatório.")

    if not normalized_email:
        raise ValueError("E-mail é obrigatório.")

    if len(password) < 12:
        raise ValueError(
            "A senha deve ter pelo menos 12 caracteres."
        )

    if normalized_role not in ALLOWED_ROLES:
        raise ValueError(
            "Função inválida. Use OWNER, ADMIN, MANAGER ou VIEWER."
        )

    company = db.get(Company, company_id)

    if company is None:
        raise ValueError("Empresa não encontrada.")

    if not company.active:
        raise ValueError("Empresa está desativada.")

    user = db.scalar(
        select(User).where(
            User.email == normalized_email,
        )
    )

    if user is not None and not update_existing:
        raise ValueError(
            "Usuário já existe. "
            "Use --update-existing para atualizá-lo "
            "ou vinculá-lo explicitamente."
        )

    if user is None:
        user = User(
            name=clean_name,
            email=normalized_email,
            password_hash=hash_password(password),
            active=True,
            is_platform_admin=False,
        )
        db.add(user)
        db.flush()

        membership = None
    else:
        membership = db.scalar(
            select(CompanyUser).where(
                CompanyUser.company_id == company.id,
                CompanyUser.user_id == user.id,
            )
        )

        user.name = clean_name
        user.password_hash = hash_password(password)
        user.active = True

    if membership is None:
        membership = CompanyUser(
            company_id=company.id,
            user_id=user.id,
            role=normalized_role,
            active=True,
        )
        db.add(membership)
    else:
        membership.role = normalized_role
        membership.active = True

    db.commit()
    db.refresh(user)
    db.refresh(membership)

    return user, membership


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Cria ou atualiza um usuário vinculado "
            "a uma empresa da SmartFoodIA."
        )
    )

    parser.add_argument(
        "--company-id",
        required=True,
    )

    parser.add_argument(
        "--name",
        required=True,
    )

    parser.add_argument(
        "--email",
        required=True,
    )

    parser.add_argument(
        "--role",
        choices=sorted(ALLOWED_ROLES),
        default="OWNER",
    )

    parser.add_argument(
        "--update-existing",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        company_id = UUID(args.company_id)
    except ValueError as exc:
        raise SystemExit(
            "UUID da empresa inválido."
        ) from exc

    password = getpass.getpass(
        "Senha do usuário: "
    )
    confirmation = getpass.getpass(
        "Confirme a senha: "
    )

    if password != confirmation:
        raise SystemExit(
            "As senhas não conferem."
        )

    with SessionLocal() as db:
        try:
            user, membership = bootstrap_company_user(
                db,
                company_id=company_id,
                name=args.name,
                email=args.email,
                password=password,
                role=args.role,
                update_existing=args.update_existing,
            )
        except ValueError as exc:
            db.rollback()
            raise SystemExit(str(exc)) from exc

    print("Usuário configurado:", user.email)
    print("Empresa:", company_id)
    print("Função:", membership.role)


if __name__ == "__main__":
    main()
