from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.modifiers import ModifierRepository
from app.schemas.modifiers import ModifierCreate, ModifierGroupCreate, ModifierGroupRead, ModifierRead

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog-modifiers"])
repository = ModifierRepository()


@router.post(
    "/modifier-groups",
    response_model=ModifierGroupRead,
    status_code=status.HTTP_201_CREATED,
)
def create_modifier_group(
    payload: ModifierGroupCreate, db: Session = Depends(get_db)
) -> ModifierGroupRead:
    return repository.create_group(db, payload)


@router.get("/modifier-groups", response_model=list[ModifierGroupRead])
def list_modifier_groups(
    store_id: UUID, db: Session = Depends(get_db)
) -> list[ModifierGroupRead]:
    return repository.list_groups(db, store_id)


@router.post(
    "/modifiers", response_model=ModifierRead, status_code=status.HTTP_201_CREATED
)
def create_modifier(
    payload: ModifierCreate, db: Session = Depends(get_db)
) -> ModifierRead:
    return repository.create_modifier(db, payload)


@router.get("/modifiers", response_model=list[ModifierRead])
def list_modifiers(store_id: UUID, db: Session = Depends(get_db)) -> list[ModifierRead]:
    return repository.list_modifiers(db, store_id)
