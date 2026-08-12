import hashlib
import hmac

from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.integration import StoreIntegration
from app.repositories.integration import IntegrationRepository


class IntegrationAuthenticationError(PermissionError):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ConsumerAuthenticator:
    def __init__(self, repository: IntegrationRepository | None = None):
        self.repository = repository or IntegrationRepository()

    def authenticate(
        self,
        db: Session,
        *,
        store_slug: str,
        authorization: str | None,
    ) -> tuple[Store, StoreIntegration]:
        store = self.repository.get_store_by_slug(db, store_slug)
        integration = (
            self.repository.get_store_integration(
                db,
                store_id=store.id,
                provider="CONSUMER",
            )
            if store
            else None
        )

        if store is None or integration is None or not integration.active:
            print(
                "CONSUMER_AUTH_FAIL "
                f"store={store_slug} reason=integration_inactive_or_missing"
            )
            raise IntegrationAuthenticationError("Loja ou integração inválida.")

        if not authorization:
            print(
                "CONSUMER_AUTH_FAIL "
                f"store={store_slug} reason=credential_missing"
            )
            raise IntegrationAuthenticationError("Token ausente ou inválido.")

        token = authorization.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        if not token:
            print(
                "CONSUMER_AUTH_FAIL "
                f"store={store_slug} reason=credential_empty"
            )
            raise IntegrationAuthenticationError("Token ausente ou inválido.")

        received_hash = hash_token(token)
        if not hmac.compare_digest(received_hash, integration.token_hash):
            print(
                "CONSUMER_AUTH_FAIL "
                f"store={store_slug} reason=credential_mismatch "
                f"credential_length={len(token)} "
                f"credential_hash_prefix={received_hash[:12]} "
                f"configured_hash_prefix={integration.token_hash[:12]}"
            )
            raise IntegrationAuthenticationError("Token ausente ou inválido.")

        return store, integration
