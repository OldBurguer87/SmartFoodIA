from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.operational_dashboard import OperationalDashboardService

router = APIRouter(
    prefix="/api/v1/operations",
    tags=["operational-dashboard"],
)
service = OperationalDashboardService()


@router.get("/stores/{store_id}/overview")
def operational_overview(
    store_id: UUID,
    hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
) -> dict:
    return service.overview(
        db,
        store_id=store_id,
        hours=hours,
    )
