from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    normalize_email,
)
from app.database.session import SessionLocal
from app.models.auth import User


def bootstrap_platform_admin(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    update_existing: bool = False,
) -> User:
    clean_name = name.strip()
    normalized_email = normalize_email(email)

    if not clean_name:
        raise ValueError("Nome é obrigatório.")

    if not normalized_email:
        raise ValueError("E-mail é obrigatório.")

    if len(password) < 12:
        raise ValueError(
            "A senha deve ter pelo menos 12 caracteres."
        )

    user = db.scalar(
        select(User).where(
            User.email == normalized_email,
        )
    )

    if user is not None:
        if not update_existing:
            raise ValueError(
                "Usuário já existe. "
                "Use --update-existing para atualizá-lo."
            )

        user.name = clean_name
        user.password_hash = hash_password(password)
        user.active = True
        user.is_platform_admin = True

        db.commit()
        db.refresh(user)

        return user

    user = User(
        name=clean_name,
        email=normalized_email,
        password_hash=hash_password(password),
        active=True,
        is_platform_admin=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Cria ou atualiza um administrador "
            "global do SmartFoodIA."
        )
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
        "--update-existing",
        action="store_true",
    )

    args = parser.parse_args()

    password = getpass.getpass(
        "Senha do administrador: "
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
            user = bootstrap_platform_admin(
                db,
                name=args.name,
                email=args.email,
                password=password,
                update_existing=args.update_existing,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    print(
        "Administrador configurado:",
        user.email,
    )


if __name__ == "__main__":
    main()
