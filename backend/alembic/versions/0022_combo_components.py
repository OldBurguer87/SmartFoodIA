"""combo components

Revision ID: 0022
Revises: 0021
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_combo_components",
        sa.Column(
            "combo_product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "component_external_code",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "component_name",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(12, 2),
            nullable=False,
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
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
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["combo_product_id"],
            ["products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_product_combo_components_combo_product_id",
        "product_combo_components",
        ["combo_product_id"],
        unique=False,
    )

    op.create_table(
        "order_item_combo_components",
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "component_external_code",
            sa.String(length=80),
            nullable=False,
        ),
        sa.Column(
            "component_name",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(12, 2),
            nullable=False,
        ),
        sa.Column(
            "total_price",
            sa.Numeric(12, 2),
            nullable=False,
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
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
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_order_item_combo_components_order_item_id",
        "order_item_combo_components",
        ["order_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_item_combo_components_order_item_id",
        table_name="order_item_combo_components",
    )
    op.drop_table("order_item_combo_components")

    op.drop_index(
        "ix_product_combo_components_combo_product_id",
        table_name="product_combo_components",
    )
    op.drop_table("product_combo_components")
