from decimal import Decimal
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.channels.whatsapp.queue import WhatsAppQueueProcessor
from app.database.base import Base
from app.models.catalog import Company, Store
from app.models.channel import ChannelAccount
from app.repositories.channel import ChannelRepository

class FakeOrchestrator:
    def reply(self, *args, **kwargs): return "Olá!"
class FakeClient:
    def send_text(self, **kwargs): return "wamid.out"

def setup():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine);db=Session(engine)
    company=Company(name="Old");db.add(company);db.flush()
    store=Store(company_id=company.id,name="Old",slug=f"old-{uuid4()}",city="Coari",state="AM",timezone="America/Manaus");db.add(store);db.flush()
    account=ChannelAccount(store_id=store.id,provider="WHATSAPP_CLOUD",external_account_id="123",verify_token_hash="hash",active=True);db.add(account);db.commit();db.refresh(account)
    return db,account

def test_queue_processes_event_and_sends_outbound():
    db,account=setup();repo=ChannelRepository()
    event=repo.create_event(db,account=account,external_event_id="wamid.in",event_type="INBOUND_MESSAGE",payload={"id":"wamid.in","from":"97999999999","type":"text","text":{"body":"Oi"}})
    result=WhatsAppQueueProcessor(repository=repo,orchestrator_factory=lambda:FakeOrchestrator(),client_factory=lambda:FakeClient()).run_once(db)
    assert result.events_processed==1
    assert result.outbound_sent==1
    assert event.status=="PROCESSED"

def test_queue_retries_failed_event():
    db,account=setup();repo=ChannelRepository()
    event=repo.create_event(db,account=account,external_event_id="wamid.bad",event_type="INBOUND_MESSAGE",payload={"id":"wamid.bad","from":"","type":"text","text":{"body":"Oi"}})
    result=WhatsAppQueueProcessor(repository=repo,orchestrator_factory=lambda:FakeOrchestrator(),max_attempts=3).run_once(db)
    assert result.events_retried==1
    assert event.status=="RETRY"
    assert event.next_attempt_at is not None
