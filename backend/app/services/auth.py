from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    generate_session_token,
    hash_session_token,
    normalize_email,
    verify_password,
)
from app.models.auth import AuthSession, CompanyUser, User
from app.models.catalog import Company, Store


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass


@dataclass
class AuthenticatedUser:
    user: User
    session: AuthSession


class AuthService:
    def login(
        self,
        db: Session,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[AuthenticatedUser, str]:
        normalized_email = normalize_email(email)

        user = db.scalar(
            select(User).where(
                User.email == normalized_email,
            )
        )

        if user is None:
            raise InvalidCredentialsError()

        if not user.active:
            raise InactiveUserError()

        if not verify_password(
            password,
            user.password_hash,
        ):
            raise InvalidCredentialsError()

        now = datetime.now(timezone.utc)
        raw_token = generate_session_token()

        session = AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=now
            + timedelta(
                hours=settings.auth_session_hours,
            ),
            last_seen_at=now,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        user.last_login_at = now

        db.add(session)
        db.commit()
        db.refresh(session)

        return (
            AuthenticatedUser(
                user=user,
                session=session,
            ),
            raw_token,
        )

    def authenticate_token(
        self,
        db: Session,
        raw_token: str,
    ) -> AuthenticatedUser | None:
        now = datetime.now(timezone.utc)

        session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == hash_session_token(raw_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )

        if session is None:
            return None

        user = db.get(User, session.user_id)

        if user is None or not user.active:
            return None

        session.last_seen_at = now
        db.commit()

        return AuthenticatedUser(
            user=user,
            session=session,
        )

    def logout(
        self,
        db: Session,
        raw_token: str,
    ) -> None:
        session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == hash_session_token(raw_token),
                AuthSession.revoked_at.is_(None),
            )
        )

        if session is None:
            return

        session.revoked_at = datetime.now(timezone.utc)
        db.commit()

    def user_companies(
        self,
        db: Session,
        user: User,
    ) -> list[dict]:
        if user.is_platform_admin:
            companies = list(
                db.scalars(
                    select(Company)
                    .where(Company.active.is_(True))
                    .order_by(Company.name)
                ).all()
            )

            result = []

            for company in companies:
                stores = list(
                    db.scalars(
                        select(Store)
                        .where(
                            Store.company_id == company.id,
                            Store.active.is_(True),
                        )
                        .order_by(Store.name)
                    ).all()
                )

                result.append(
                    {
                        "id": str(company.id),
                        "name": company.name,
                        "role": "PLATFORM_ADMIN",
                        "stores": [
                            {
                                "id": str(store.id),
                                "name": store.name,
                                "slug": store.slug,
                                "city": store.city,
                                "state": store.state,
                                "timezone": store.timezone,
                            }
                            for store in stores
                        ],
                    }
                )

            return result

        memberships = list(
            db.scalars(
                select(CompanyUser).where(
                    CompanyUser.user_id == user.id,
                    CompanyUser.active.is_(True),
                )
            ).all()
        )

        result = []

        for membership in memberships:
            company = db.get(
                Company,
                membership.company_id,
            )

            if company is None or not company.active:
                continue

            stores = list(
                db.scalars(
                    select(Store)
                    .where(
                        Store.company_id == company.id,
                        Store.active.is_(True),
                    )
                    .order_by(Store.name)
                ).all()
            )

            result.append(
                {
                    "id": str(company.id),
                    "name": company.name,
                    "role": membership.role,
                    "stores": [
                        {
                            "id": str(store.id),
                            "name": store.name,
                            "slug": store.slug,
                            "city": store.city,
                            "state": store.state,
                            "timezone": store.timezone,
                        }
                        for store in stores
                    ],
                }
            )

        return result

    def can_access_store(
        self,
        db: Session,
        user: User,
        store_id: UUID,
    ) -> bool:
        store = db.get(Store, store_id)

        if store is None or not store.active:
            return False

        if user.is_platform_admin:
            return True

        membership = db.scalar(
            select(CompanyUser).where(
                CompanyUser.user_id == user.id,
                CompanyUser.company_id == store.company_id,
                CompanyUser.active.is_(True),
            )
        )

        return membership is not None


@dataclass
class StoreAccess:
    store_id: UUID
    company_id: UUID
    role: str
    is_platform_admin: bool

    @property
    def can_write(self) -> bool:
        if self.is_platform_admin:
            return True

        return self.role in {
            "OWNER",
            "ADMIN",
            "MANAGER",
        }


def resolve_store_access(
    db: Session,
    user: User,
    store_id: UUID,
) -> StoreAccess | None:
    store = db.get(Store, store_id)

    if store is None or not store.active:
        return None

    if user.is_platform_admin:
        return StoreAccess(
            store_id=store.id,
            company_id=store.company_id,
            role="PLATFORM_ADMIN",
            is_platform_admin=True,
        )

    membership = db.scalar(
        select(CompanyUser).where(
            CompanyUser.user_id == user.id,
            CompanyUser.company_id == store.company_id,
            CompanyUser.active.is_(True),
        )
    )

    if membership is None:
        return None

    return StoreAccess(
        store_id=store.id,
        company_id=store.company_id,
        role=membership.role,
        is_platform_admin=False,
    )
