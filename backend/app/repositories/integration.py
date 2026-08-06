from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.integration import StoreIntegration


class IntegrationRepository:
    def get_store_by_slug(self, db: Session, store_slug: str) -> Store | None:
        return db.scalar(
            select(Store).where(
                Store.slug == store_slug,
                Store.active.is_(True),
            )
        )

    def get_store_integration(
        self,
        db: Session,
        *,
        store_id: UUID,
        provider: str,
    ) -> StoreIntegration | None:
        return db.scalar(
            select(StoreIntegration).where(
                StoreIntegration.store_id == store_id,
                StoreIntegration.provider == provider,
                StoreIntegration.active.is_(True),
            )
        )
