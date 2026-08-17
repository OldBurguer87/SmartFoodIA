from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.database.session import get_db
from app.services.auth import (
    AuthenticatedUser,
    StoreAccess,
    resolve_store_access,
)


def require_store_access(
    store_id: UUID,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> StoreAccess:
    access = resolve_store_access(
        db,
        authenticated.user,
        store_id,
    )

    if access is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a esta loja.",
        )

    return access


def require_store_write_access(
    access: StoreAccess = Depends(
        require_store_access,
    ),
) -> StoreAccess:
    if not access.can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não pode alterar esta loja.",
        )

    return access
