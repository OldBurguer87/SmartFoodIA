from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    require_platform_admin,
    require_store_access,
)
from app.database.session import get_db
from app.services.auth import AuthenticatedUser, StoreAccess
from app.services.operational_dashboard_recent import (
    RecentOperationalDashboardService,
)
from app.services.platform_dashboard import (
    PlatformDashboardService,
)

router = APIRouter(
    prefix="/api/v1/operations",
    tags=["operational-dashboard"],
)

service = RecentOperationalDashboardService()
platform_service = PlatformDashboardService()


@router.get("/overview")
def platform_overview(
    hours: int = Query(default=24, ge=1, le=720),
    _authenticated: AuthenticatedUser = Depends(
        require_platform_admin,
    ),
    db: Session = Depends(get_db),
) -> dict:
    return platform_service.overview(
        db,
        hours=hours,
    )


@router.get("/stores/{store_id}/overview")
def operational_overview(
    store_id: UUID,
    hours: int = Query(default=24, ge=1, le=720),
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
