from __future__ import annotations

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.services.auth import (
    AuthService,
    AuthenticatedUser,
    InactiveUserError,
    InvalidCredentialsError,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)

service = AuthService()


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=255,
    )
    password: str = Field(
        min_length=8,
        max_length=200,
    )


def current_auth(
    session_token: str | None = Cookie(
        default=None,
        alias=settings.auth_cookie_name,
    ),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        )

    authenticated = service.authenticate_token(
        db,
        session_token,
    )

    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
        )

    return authenticated


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    forwarded_for = request.headers.get(
        "x-forwarded-for",
    )

    if forwarded_for:
        ip_address = (
            forwarded_for.split(",", 1)[0].strip()
        )
    elif request.client:
        ip_address = request.client.host
    else:
        ip_address = None

    try:
        authenticated, raw_token = service.login(
            db,
            email=payload.email,
            password=payload.password,
            user_agent=request.headers.get(
                "user-agent",
            ),
            ip_address=ip_address,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado.",
        )

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.auth_session_hours * 3600,
        path="/",
    )

    return {
        "authenticated": True,
        "user": {
            "id": str(authenticated.user.id),
            "name": authenticated.user.name,
            "email": authenticated.user.email,
            "is_platform_admin": (
                authenticated.user.is_platform_admin
            ),
        },
        "companies": service.user_companies(
            db,
            authenticated.user,
        ),
    }


@router.get("/me")
def me(
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> dict:
    user = authenticated.user

    return {
        "authenticated": True,
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "is_platform_admin": (
                user.is_platform_admin
            ),
        },
        "companies": service.user_companies(
            db,
            user,
        ),
    }


@router.post("/logout")
def logout(
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias=settings.auth_cookie_name,
    ),
    db: Session = Depends(get_db),
) -> dict:
    if session_token:
        service.logout(
            db,
            session_token,
        )

    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )

    return {
        "authenticated": False,
    }
