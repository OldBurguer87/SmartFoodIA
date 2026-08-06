from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.ai.tools.context import ToolContext
from app.ai.tools.registry import OliviaToolRegistry, UnknownToolError
from app.database.session import get_db
from app.repositories.integration import IntegrationRepository
from app.schemas.olivia import ToolExecutionRequest, ToolExecutionResponse

router = APIRouter(prefix="/api/v1/olivia", tags=["olivia-tools"])
integration_repository = IntegrationRepository()


@router.get("/stores/{store_slug}/tools")
def list_tools(
    store_slug: str,
    db: Session = Depends(get_db),
) -> list[dict]:
    store = integration_repository.get_store_by_slug(db, store_slug)
    if store is None:
        raise HTTPException(status_code=404, detail="Loja não encontrada.")
    registry = OliviaToolRegistry(ToolContext(db=db, store_id=store.id))
    return registry.openai_definitions()


@router.post(
    "/stores/{store_slug}/tools/execute",
    response_model=ToolExecutionResponse,
)
def execute_tool(
    store_slug: str,
    payload: ToolExecutionRequest,
    x_customer_phone: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ToolExecutionResponse:
    store = integration_repository.get_store_by_slug(db, store_slug)
    if store is None:
        raise HTTPException(status_code=404, detail="Loja não encontrada.")

    registry = OliviaToolRegistry(
        ToolContext(
            db=db,
            store_id=store.id,
            customer_phone=x_customer_phone,
        )
    )
    try:
        result = registry.execute(payload.tool_name, payload.arguments)
    except UnknownToolError as error:
        raise HTTPException(status_code=404, detail="Ferramenta não encontrada.") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return ToolExecutionResponse(
        ok=result.ok,
        data=result.data,
        error=result.error,
        requires_human=result.requires_human,
    )
