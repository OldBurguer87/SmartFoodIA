from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db

router = APIRouter(tags=["system"])


@router.get("/live")
def live() -> dict[str, str]:
    return {
        "status": "alive",
        "application": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Banco de dados indisponível.",
        ) from error

    return {
        "status": "ready",
        "application": settings.app_name,
        "database": "available",
    }
