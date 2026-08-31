"""store delivery places

Revision ID: 0023
Revises: 0022
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_delivery_places",
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "place_type",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "normalized_name",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "aliases",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "street",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "number",
            sa.String(length=40),
            nullable=False,
        ),
        sa.Column(
            "neighborhood",
            sa.String(length=140),
            nullable=False,
        ),
        sa.Column(
            "city",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(length=2),
            nullable=False,
        ),
        sa.Column(
            "postal_code",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "reference",
            sa.String(length=240),
            nullable=True,
        ),
        sa.Column(
            "source_url",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "normalized_name",
            name="uq_store_delivery_place_normalized_name",
        ),
    )

    op.create_index(
        "ix_store_delivery_places_store_id",
        "store_delivery_places",
        ["store_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_store_delivery_places_store_id",
        table_name="store_delivery_places",
    )
    op.drop_table("store_delivery_places")
