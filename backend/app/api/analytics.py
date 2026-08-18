from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_store_access
from app.database.session import get_db
from app.services.auth import StoreAccess
from app.services.store_analytics import StoreAnalyticsService


router = APIRouter(
    prefix="/api/v1/operations/stores",
    tags=["analytics"],
)

service = StoreAnalyticsService()


@router.get("/{store_id}/analytics")
def store_analytics(
    store_id: UUID,
    hours: int = Query(
        default=24,
        ge=1,
        le=8760,
    ),
    _access: StoreAccess = Depends(
        require_store_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    return service.overview(
        db,
        store_id=store_id,
        hours=hours,
    )
