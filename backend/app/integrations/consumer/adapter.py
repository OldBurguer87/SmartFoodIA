from __future__ import annotations
from datetime import timezone
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.integrations.contracts.orders import IntegrationEvent
from app.integrations.consumer.mapper import map_order
from app.integrations.consumer.status import STATUS_TO_INTERNAL, INTERNAL_EVENT
from app.models.order import OrderEvent
from app.repositories.order import OrderRepository

class IntegrationOrderNotFound(LookupError): pass
class IntegrationStatusError(ValueError): pass

class ConsumerPartnerAdapter:
    provider='CONSUMER'
    def __init__(self, order_repository: OrderRepository | None=None): self.orders=order_repository or OrderRepository()
    def poll(self, db: Session, *, store_id: UUID, limit: int=100):
        return [IntegrationEvent(e.id,e.order_id,e.created_at.astimezone(timezone.utc),e.code,e.full_code) for e in self.orders.list_pending_events(db,store_id=store_id,limit=limit)]
    def serialize_order(self, db: Session, *, store_id: UUID, order_id: UUID, integration):
        order=self.orders.get_for_store(db,store_id=store_id,order_id=order_id)
        if not order: raise IntegrationOrderNotFound('Pedido não encontrado.')
        return map_order(order,integration)
    def acknowledge_details_request(self, db: Session, *, store_id: UUID, order_id: UUID, code: str, full_code: str, reason: str|None=None):
        order=self.orders.get_for_store(db,store_id=store_id,order_id=order_id)
        if not order: raise IntegrationOrderNotFound('Pedido não encontrado.')
        normalized=code.strip().upper()
        normalized_full=(full_code or 'ORDER_DETAILS_REQUESTED').strip().upper()
        if normalized != 'ODR' or normalized_full != 'ORDER_DETAILS_REQUESTED':
            raise IntegrationStatusError(
                'Evento suportado neste endpoint: ODR / ORDER_DETAILS_REQUESTED.'
            )
        full_code=normalized_full
        existing=next((e for e in order.events if e.code==normalized and e.full_code==full_code),None)
        if existing: return IntegrationEvent(existing.id,existing.order_id,existing.created_at.astimezone(timezone.utc),existing.code,existing.full_code)
        if normalized=='ODR':
            for event in order.events:
                if event.code=='PLC' and event.status=='PENDING': event.status='DELIVERED'
        event=OrderEvent(id=uuid4(),order_id=order.id,code=normalized,full_code=full_code or 'ORDER_DETAILS_REQUESTED',status='DELIVERED',reason=reason)
        db.add(event); db.commit(); db.refresh(event)
        return IntegrationEvent(event.id,event.order_id,event.created_at.astimezone(timezone.utc),event.code,event.full_code)
    def apply_external_status(self, db: Session, *, store_id: UUID, order_id: UUID, status: str, justification: str|None=None):
        order=self.orders.get_for_store(db,store_id=store_id,order_id=order_id)
        if not order: raise IntegrationOrderNotFound('Pedido não encontrado.')
        normalized=status.strip().upper(); internal=STATUS_TO_INTERNAL.get(normalized)
        if not internal: raise IntegrationStatusError(f'Status não suportado: {status}.')
        if order.status==internal: return internal,False
        order.status=internal; code,full=INTERNAL_EVENT[internal]
        db.add(OrderEvent(order_id=order.id,code=code,full_code=full,status='DELIVERED',reason=justification)); db.commit()
        return internal,True
