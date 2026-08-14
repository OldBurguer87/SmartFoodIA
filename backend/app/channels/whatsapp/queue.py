from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from sqlalchemy.orm import Session
from app.ai.orchestrator import OliviaOrchestrator
from app.ai.providers.openai_provider import OpenAIResponsesProvider
from app.channels.whatsapp.client import WhatsAppCloudClient
from app.channels.whatsapp.service import WhatsAppGatewayService
from app.repositories.channel import ChannelRepository

@dataclass(frozen=True)
class QueueRunResult:
    events_processed: int = 0
    events_retried: int = 0
    events_dead: int = 0
    outbound_sent: int = 0
    outbound_retried: int = 0
    outbound_dead: int = 0

class WhatsAppQueueProcessor:
    def __init__(self, *, repository=None, orchestrator_factory=None, client_factory: Callable[[], WhatsAppCloudClient] | None=None, max_attempts:int=5):
        self.repository=repository or ChannelRepository()
        self.orchestrator_factory=orchestrator_factory or (lambda: OliviaOrchestrator(OpenAIResponsesProvider()))
        self.client_factory=client_factory
        self.max_attempts=max_attempts

    def run_once(self, db: Session, *, limit:int=50) -> QueueRunResult:
        now=datetime.now(timezone.utc)
        ep=er=ed=osent=orr=od=0
        gateway=WhatsAppGatewayService(repository=self.repository, orchestrator_factory=self.orchestrator_factory, client_factory=None)
        for event in self.repository.list_due_events(db, now=now, limit=limit):
            account=self.repository.get_account(db,event.channel_account_id)
            try:
                gateway.process_event(db, account, event)
                event.status='PROCESSED';event.processed_at=now;event.error_message=None;ep+=1
            except Exception as exc:
                event.attempts += 1;event.error_message=str(exc)
                if event.attempts >= self.max_attempts:
                    event.status='DEAD';ed+=1
                else:
                    event.status='RETRY';event.next_attempt_at=now+timedelta(seconds=min(300,2**event.attempts));er+=1
            db.commit()
        if self.client_factory is not None:
            client=self.client_factory()
            for msg in self.repository.list_due_outbound(db, now=now, limit=limit):
                account=self.repository.get_account(db,msg.channel_account_id)
                try:
                    msg.attempts += 1
                    if msg.content_type == "DOCUMENT":
                        document = json.loads(msg.content)
                        msg.external_message_id = client.send_document(
                            phone_number_id=account.external_account_id,
                            recipient=msg.recipient,
                            document_url=document["url"],
                            filename=document["filename"],
                            caption=document.get("caption"),
                        )
                    else:
                        msg.external_message_id=client.send_text(phone_number_id=account.external_account_id,recipient=msg.recipient,text=msg.content)
                    msg.status='SENT';msg.sent_at=now;msg.error_message=None;osent+=1
                except Exception as exc:
                    msg.error_message=str(exc)
                    if msg.attempts >= self.max_attempts:
                        msg.status='DEAD';od+=1
                    else:
                        msg.status='RETRY';msg.next_attempt_at=now+timedelta(seconds=min(300,2**msg.attempts));orr+=1
                db.commit()
        return QueueRunResult(ep,er,ed,osent,orr,od)
