from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.consumer.adapter import (
    ConsumerPartnerAdapter,
    IntegrationOrderNotFound,
    IntegrationStatusError,
)
from app.integrations.consumer.auth import (
    ConsumerAuthenticator,
    IntegrationAuthenticationError,
    hash_token,
)
from app.integrations.notifications import WhatsAppOrderStatusNotifier
from app.models.catalog import Store
from app.models.integration import StoreIntegration
from app.schemas.consumer import (
    ConsumerDiagnosticsResponse,
    ConsumerEndpointSet,
    ConsumerEventRead,
    ConsumerPollingResponse,
    ConsumerStatusResponse,
)

ConsumerAuthenticationError = IntegrationAuthenticationError
ConsumerNotFoundError = IntegrationOrderNotFound
ConsumerValidationError = IntegrationStatusError


class ConsumerPartnerService:
    def __init__(self, adapter=None, authenticator=None, notifier=None):
        self.adapter = adapter or ConsumerPartnerAdapter()
        self.authenticator = authenticator or ConsumerAuthenticator()
        self.notifier = notifier or WhatsAppOrderStatusNotifier()

    def authenticate(
        self,
        db: Session,
        *,
        store_slug: str,
        authorization: str | None,
    ):
        return self.authenticator.authenticate(
            db,
            store_slug=store_slug,
            authorization=authorization,
        )

    def diagnostics(
        self,
        db: Session,
        *,
        store: Store,
        integration: StoreIntegration,
        base_url: str,
    ) -> ConsumerDiagnosticsResponse:
        normalized_base = base_url.rstrip("/")
        prefix = (
            f"{normalized_base}/api/v1/integrations/consumer/{store.slug}"
        )
        pending = self.adapter.poll(db, store_id=store.id, limit=500)
        merchant_ready = bool(
            integration.merchant_external_id and integration.merchant_name
        )
        return ConsumerDiagnosticsResponse(
            storeSlug=store.slug,
            storeName=store.name,
            provider=integration.provider,
            integrationActive=integration.active,
            merchantId=integration.merchant_external_id,
            merchantName=integration.merchant_name,
            pendingEvents=len(pending),
            endpoints=ConsumerEndpointSet(
                polling=f"{prefix}/events",
                orderDetails=f"{prefix}/orders/{{order_id}}",
                orderEvent=f"{prefix}/orders/{{order_id}}/events",
                orderStatus=f"{prefix}/orders/{{order_id}}/status",
            ),
            checks={
                "integration_active": bool(integration.active),
                "merchant_configured": merchant_ready,
                "token_configured": bool(integration.token_hash),
                "https_base_url": normalized_base.startswith("https://"),
                "store_slug_configured": bool(store.slug),
            },
            reasonPhrase="Diagnóstico da integração Consumer concluído.",
        )

    def polling(self, db: Session, *, store: Store, limit: int = 100):
        events = self.adapter.poll(db, store_id=store.id, limit=limit)
        return ConsumerPollingResponse(
            items=[
                ConsumerEventRead(
                    id=event.id,
                    orderId=event.order_id,
                    createdAt=event.created_at,
                    fullCode=event.full_code,
                    code=event.code,
                )
                for event in events
            ]
        )

    def order_details(
        self,
        db: Session,
        *,
        store: Store,
        integration: StoreIntegration,
        order_id: UUID,
    ):
        return self.adapter.serialize_order(
            db,
            store_id=store.id,
            order_id=order_id,
            integration=integration,
        )

    def receive_order_event(self, db: Session, *, store: Store, payload):
        event = self.adapter.acknowledge_details_request(
            db,
            store_id=store.id,
            order_id=payload.OrderId,
            code=payload.EventCode,
            full_code=payload.EventFullCode or "ORDER_DETAILS_REQUESTED",
            reason=payload.EventFull,
        )
        return ConsumerEventRead(
            id=event.id,
            orderId=event.order_id,
            createdAt=event.created_at,
            fullCode=event.full_code,
            code=event.code,
        )

    def update_status(self, db: Session, *, store: Store, payload):
        status, changed = self.adapter.apply_external_status(
            db,
            store_id=store.id,
            order_id=payload.orderId,
            status=payload.status,
            justification=payload.justification,
        )
        phrase = (
            f"{payload.orderId} alterado para '{status}'"
            if changed
            else f"{payload.orderId} já estava com status '{status}'"
        )
        if changed:
            self.notifier.notify_status_change(
                db,
                store_id=store.id,
                order_id=payload.orderId,
                status=status,
            )
        if changed and payload.justification:
            phrase += f": {payload.justification}"
        return ConsumerStatusResponse(reasonPhrase=phrase + ".")


__all__ = [
    "ConsumerAuthenticationError",
    "ConsumerNotFoundError",
    "ConsumerPartnerService",
    "ConsumerValidationError",
    "hash_token",
]
