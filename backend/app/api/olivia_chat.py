from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.ai.orchestrator import OliviaExecutionError, OliviaOrchestrator
from app.ai.providers.openai_provider import (
    OpenAIProviderConfigurationError,
    OpenAIResponsesProvider,
)
from app.database.session import get_db
from app.schemas.olivia import OliviaReplyRequest, OliviaReplyResponse

router = APIRouter(prefix="/api/v1/olivia", tags=["olivia-chat"])

@router.post("/reply", response_model=OliviaReplyResponse)
def reply(payload: OliviaReplyRequest, db: Session = Depends(get_db)) -> OliviaReplyResponse:
    try:
        text = OliviaOrchestrator(OpenAIResponsesProvider()).reply(
            db,
            store_id=payload.store_id,
            conversation_id=payload.conversation_id,
            customer_message=payload.message,
            customer_phone=payload.customer_phone,
        )
    except OpenAIProviderConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OliviaExecutionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return OliviaReplyResponse(conversation_id=payload.conversation_id, reply=text)
