from fastapi import FastAPI

from app.api.catalog import router as catalog_router
from app.api.modifiers import router as modifiers_router
from app.api.customers import router as customers_router
from app.api.carts import router as carts_router
from app.api.orders import router as orders_router
from app.api.consumer_partner import router as consumer_partner_router
from app.api.olivia_tools import router as olivia_tools_router
from app.api.olivia_chat import router as olivia_chat_router
from app.api.conversations import router as conversations_router
from app.api.whatsapp import router as whatsapp_router
from app.api.system import router as system_router
from app.api.operations import router as operations_router
from app.api.support_operations import router as support_operations_router
from app.api.operational_dashboard import router as operational_dashboard_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
)

app.include_router(catalog_router)
app.include_router(modifiers_router)
app.include_router(customers_router)
app.include_router(carts_router)
app.include_router(orders_router)
app.include_router(consumer_partner_router)
app.include_router(olivia_tools_router)
app.include_router(olivia_chat_router)
app.include_router(conversations_router)
app.include_router(whatsapp_router)
app.include_router(system_router)
app.include_router(operations_router)
app.include_router(support_operations_router)
app.include_router(operational_dashboard_router)


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
