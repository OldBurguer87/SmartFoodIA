from app.channels.whatsapp.client import WhatsAppCloudClient
from app.channels.whatsapp.queue import WhatsAppQueueProcessor
from app.core.config import settings
from app.database.session import SessionLocal

def make_client():
    if not settings.whatsapp_access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN não configurado.")
    return WhatsAppCloudClient(access_token=settings.whatsapp_access_token, graph_api_version=settings.whatsapp_graph_api_version, timeout_seconds=settings.whatsapp_timeout_seconds)

def main():
    with SessionLocal() as db:
        result=WhatsAppQueueProcessor(client_factory=make_client).run_once(db)
    print(result)
if __name__ == "__main__": main()
