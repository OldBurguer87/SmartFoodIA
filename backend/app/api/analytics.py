from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    require_platform_admin,
    require_store_access,
)
from app.database.session import get_db
from app.services.auth import (
    AuthenticatedUser,
    StoreAccess,
)
from app.services.platform_analytics import (
    PlatformAnalyticsService,
)
from app.services.store_analytics import (
    StoreAnalyticsService,
)


router = APIRouter(
    tags=["analytics"],
)

store_router = APIRouter(
    prefix="/api/v1/operations/stores",
)

platform_router = APIRouter(
    prefix="/api/v1/operations/platform",
)

store_service = StoreAnalyticsService()
platform_service = PlatformAnalyticsService()


@store_router.get("/{store_id}/analytics")
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
    return store_service.overview(
        db,
        store_id=store_id,
        hours=hours,
    )


@platform_router.get("/analytics")
def platform_analytics(
    hours: int = Query(
        default=24,
        ge=1,
        le=8760,
    ),
    _authenticated: AuthenticatedUser = Depends(
        require_platform_admin,
    ),
    db: Session = Depends(get_db),
) -> dict:
    return platform_service.overview(
        db,
        hours=hours,
    )


router.include_router(store_router)
router.include_router(platform_router)
