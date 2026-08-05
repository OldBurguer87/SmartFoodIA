from fastapi import FastAPI

from app.api.catalog import router as catalog_router
from app.api.modifiers import router as modifiers_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
)

app.include_router(catalog_router)
app.include_router(modifiers_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "status": "online",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "application": settings.app_name}


@app.get("/version")
def version() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }
