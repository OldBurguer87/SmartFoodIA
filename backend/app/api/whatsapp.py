from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.channels.whatsapp.client import WhatsAppCloudClient
from app.channels.whatsapp.security import hash_verify_token, verify_meta_signature
from app.channels.whatsapp.service import WhatsAppGatewayService
from app.core.config import settings
from app.database.session import get_db
from app.repositories.channel import ChannelRepository

router = APIRouter(prefix="/api/v1/channels/whatsapp", tags=["whatsapp"])
repository = ChannelRepository()


def make_client() -> WhatsAppCloudClient:
    if not settings.whatsapp_access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN não configurado.")
    return WhatsAppCloudClient(
        access_token=settings.whatsapp_access_token,
        graph_api_version=settings.whatsapp_graph_api_version,
        timeout_seconds=settings.whatsapp_timeout_seconds,
    )


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
    db: Session = Depends(get_db),
) -> str:
    account = repository.get_account_by_verify_token_hash(
        db,
        provider="WHATSAPP_CLOUD",
        verify_token_hash=hash_verify_token(hub_verify_token),
    )
    if hub_mode != "subscribe" or account is None:
        raise HTTPException(status_code=403, detail="Verificação inválida.")
    return hub_challenge


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    if not verify_meta_signature(
        raw_body,
        x_hub_signature_256,
        settings.whatsapp_app_secret,
    ):
        raise HTTPException(status_code=401, detail="Assinatura inválida.")
    payload = await request.json()
    result = WhatsAppGatewayService(client_factory=make_client, process_inline=False).process_payload(
        db,
        payload,
    )
    return {
        "received": result.received,
        "processed": result.processed,
        "duplicated": result.duplicated,
        "ignored": result.ignored,
        "failed": result.failed,
    }
