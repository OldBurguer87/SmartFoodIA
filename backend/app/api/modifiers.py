from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.database.session import get_db
from app.repositories.modifiers import ModifierRepository
from app.schemas.modifiers import (
    ModifierCreate,
    ModifierGroupCreate,
    ModifierGroupRead,
    ModifierRead,
)
from app.services.auth import (
    AuthenticatedUser,
    resolve_store_access,
)

router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["catalog-modifiers"],
)

repository = ModifierRepository()


def require_modifier_write_access(
    db: Session,
    authenticated: AuthenticatedUser,
    *,
    store_id: UUID,
) -> None:
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

    if not access.can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não pode alterar esta loja.",
        )


@router.post(
    "/modifier-groups",
    response_model=ModifierGroupRead,
    status_code=status.HTTP_201_CREATED,
)
def create_modifier_group(
    payload: ModifierGroupCreate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> ModifierGroupRead:
    require_modifier_write_access(
        db,
        authenticated,
        store_id=payload.store_id,
    )

    return repository.create_group(
        db,
        payload,
    )


@router.get(
    "/modifier-groups",
    response_model=list[ModifierGroupRead],
)
def list_modifier_groups(
    store_id: UUID,
    db: Session = Depends(get_db),
) -> list[ModifierGroupRead]:
    return repository.list_groups(
        db,
        store_id,
    )


@router.post(
    "/modifiers",
    response_model=ModifierRead,
    status_code=status.HTTP_201_CREATED,
)
def create_modifier(
    payload: ModifierCreate,
    authenticated: AuthenticatedUser = Depends(
        current_auth,
    ),
    db: Session = Depends(get_db),
) -> ModifierRead:
    require_modifier_write_access(
        db,
        authenticated,
        store_id=payload.store_id,
    )

    return repository.create_modifier(
        db,
        payload,
    )


@router.get(
    "/modifiers",
    response_model=list[ModifierRead],
)
def list_modifiers(
    store_id: UUID,
    db: Session = Depends(get_db),
) -> list[ModifierRead]:
    return repository.list_modifiers(
        db,
        store_id,
    )
