import hashlib
import hmac
from sqlalchemy.orm import Session
from app.models.catalog import Store
from app.models.integration import StoreIntegration
from app.repositories.integration import IntegrationRepository

class IntegrationAuthenticationError(PermissionError): pass

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

class ConsumerAuthenticator:
    def __init__(self, repository: IntegrationRepository | None = None):
        self.repository = repository or IntegrationRepository()
    def authenticate(self, db: Session, *, store_slug: str, authorization: str | None) -> tuple[Store, StoreIntegration]:
        store=self.repository.get_store_by_slug(db, store_slug)
        integration = self.repository.get_store_integration(db, store_id=store.id, provider='CONSUMER') if store else None
        if store is None or integration is None or not integration.active:
            raise IntegrationAuthenticationError('Loja ou integração inválida.')
        if not authorization or not authorization.startswith('Bearer '):
            raise IntegrationAuthenticationError('Token ausente ou inválido.')
        token=authorization.removeprefix('Bearer ').strip()
        if not token or not hmac.compare_digest(hash_token(token), integration.token_hash):
            raise IntegrationAuthenticationError('Token ausente ou inválido.')
        return store, integration
