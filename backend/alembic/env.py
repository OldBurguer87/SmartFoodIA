from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.database.base import Base
from app.models.catalog import (  # noqa: F401
    Category,
    Company,
    Modifier,
    ModifierGroup,
    ModifierGroupItem,
    Product,
    ProductFamily,
    ProductModifierGroup,
    Store,
)
from app.models.customer import Customer, CustomerAddress  # noqa: F401
from app.models.cart import Cart, CartItem, CartItemModifier  # noqa: F401
from app.models.order import (  # noqa: F401
    Order,
    OrderEvent,
    OrderItem,
    OrderItemModifier,
)
from app.models.integration import StoreIntegration  # noqa: F401
from app.models.channel import ChannelAccount, ChannelEvent, OutboundChannelMessage  # noqa: F401
from app.models.conversation import (  # noqa: F401
    AIEvent,
    Conversation,
    HumanTicket,
    KnowledgeGap,
    Message,
)
from app.models.commercial import (  # noqa: F401
    StoreBusinessHours,
    StoreCommercialRules,
    StoreDeliveryZone,
)
from app.models.menu import StoreMenuDocument  # noqa: F401
from app.models.staff import StoreStaffMember  # noqa: F401
from app.models.payment import PaymentReceipt  # noqa: F401
from app.models.auth import AuthSession, CompanyUser, User  # noqa: F401
from app.models.catalog_version import (  # noqa: F401
    CatalogSourceFile,
    CatalogVersion,
    StoreCatalogConfig,
)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
