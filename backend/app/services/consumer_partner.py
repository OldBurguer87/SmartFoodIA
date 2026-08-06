from uuid import UUID
from sqlalchemy.orm import Session
from app.integrations.consumer.adapter import ConsumerPartnerAdapter, IntegrationOrderNotFound, IntegrationStatusError
from app.integrations.consumer.auth import ConsumerAuthenticator, IntegrationAuthenticationError, hash_token
from app.models.catalog import Store
from app.models.integration import StoreIntegration
from app.schemas.consumer import ConsumerEventRead, ConsumerPollingResponse, ConsumerStatusResponse
from app.integrations.notifications import WhatsAppOrderStatusNotifier

ConsumerAuthenticationError=IntegrationAuthenticationError
ConsumerNotFoundError=IntegrationOrderNotFound
ConsumerValidationError=IntegrationStatusError

class ConsumerPartnerService:
    def __init__(self, adapter=None, authenticator=None, notifier=None):
        self.adapter=adapter or ConsumerPartnerAdapter()
        self.authenticator=authenticator or ConsumerAuthenticator()
        self.notifier=notifier or WhatsAppOrderStatusNotifier()
    def authenticate(self, db: Session, *, store_slug: str, authorization: str|None): return self.authenticator.authenticate(db,store_slug=store_slug,authorization=authorization)
    def polling(self, db: Session, *, store: Store, limit: int=100):
        events=self.adapter.poll(db,store_id=store.id,limit=limit)
        return ConsumerPollingResponse(items=[ConsumerEventRead(id=e.id,orderId=e.order_id,createdAt=e.created_at,fullCode=e.full_code,code=e.code) for e in events])
    def order_details(self, db: Session, *, store: Store, integration: StoreIntegration, order_id: UUID): return self.adapter.serialize_order(db,store_id=store.id,order_id=order_id,integration=integration)
    def receive_order_event(self, db: Session, *, store: Store, payload):
        e=self.adapter.acknowledge_details_request(db,store_id=store.id,order_id=payload.OrderId,code=payload.EventCode,full_code=payload.EventFullCode or 'ORDER_DETAILS_REQUESTED',reason=payload.EventFull)
        return ConsumerEventRead(id=e.id,orderId=e.order_id,createdAt=e.created_at,fullCode=e.full_code,code=e.code)
    def update_status(self, db: Session, *, store: Store, payload):
        status,changed=self.adapter.apply_external_status(db,store_id=store.id,order_id=payload.orderId,status=payload.status,justification=payload.justification)
        phrase=(f"{payload.orderId} alterado para '{status}'" if changed else f"{payload.orderId} já estava com status '{status}'")
        if changed:
            self.notifier.notify_status_change(
                db,
                store_id=store.id,
                order_id=payload.orderId,
                status=status,
            )
        if changed and payload.justification:
            phrase += f': {payload.justification}'
        return ConsumerStatusResponse(reasonPhrase=phrase+'.')
