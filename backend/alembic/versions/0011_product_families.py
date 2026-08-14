"""Add product families and product variation relationships.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("external_code", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("selection_name", sa.String(length=80), nullable=True),
        sa.Column(
            "selection_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
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
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "external_code",
            name="uq_product_family_store_external_code",
        ),
    )

    op.create_index(
        "ix_product_families_store_id",
        "product_families",
        ["store_id"],
    )

    op.create_index(
        "ix_product_families_name",
        "product_families",
        ["name"],
    )

    op.add_column(
        "products",
        sa.Column(
            "family_id",
            sa.Uuid(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_products_family_id",
        "products",
        "product_families",
        ["family_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_products_family_id",
        "products",
        ["family_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_products_family_id",
        table_name="products",
    )

    op.drop_constraint(
        "fk_products_family_id",
        "products",
        type_="foreignkey",
    )

    op.drop_column(
        "products",
        "family_id",
    )

    op.drop_index(
        "ix_product_families_name",
        table_name="product_families",
    )

    op.drop_index(
        "ix_product_families_store_id",
        table_name="product_families",
    )

    op.drop_table("product_families")
