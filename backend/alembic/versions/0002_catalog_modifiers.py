"""Create modifier groups and compatibility tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "modifier_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("min_select", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_select", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("allow_repeat", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "name", name="uq_modifier_group_store_name"),
        sa.CheckConstraint("min_select >= 0", name="ck_modifier_group_min_nonnegative"),
        sa.CheckConstraint("max_select >= 1", name="ck_modifier_group_max_positive"),
        sa.CheckConstraint("min_select <= max_select", name="ck_modifier_group_limits"),
    )
    op.create_table(
        "modifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("external_code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "external_code", name="uq_modifier_store_external_code"),
        sa.CheckConstraint("price >= 0", name="ck_modifier_price_nonnegative"),
    )
    op.create_index("ix_modifiers_name", "modifiers", ["name"], unique=False)
    op.create_table(
        "product_modifier_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("modifier_group_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_select_override", sa.Integer(), nullable=True),
        sa.Column("max_select_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["modifier_group_id"], ["modifier_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "modifier_group_id", name="uq_product_modifier_group"),
    )
    op.create_table(
        "modifier_group_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("modifier_group_id", sa.Uuid(), nullable=False),
        sa.Column("modifier_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("default_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["modifier_group_id"], ["modifier_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["modifier_id"], ["modifiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("modifier_group_id", "modifier_id", name="uq_modifier_group_item"),
        sa.CheckConstraint("min_quantity >= 0", name="ck_group_item_min_nonnegative"),
        sa.CheckConstraint("max_quantity >= 1", name="ck_group_item_max_positive"),
        sa.CheckConstraint("min_quantity <= max_quantity", name="ck_group_item_limits"),
        sa.CheckConstraint(
            "default_quantity >= min_quantity AND default_quantity <= max_quantity",
            name="ck_group_item_default_bounds",
        ),
    )


def downgrade() -> None:
    op.drop_table("modifier_group_items")
    op.drop_table("product_modifier_groups")
    op.drop_index("ix_modifiers_name", table_name="modifiers")
    op.drop_table("modifiers")
    op.drop_table("modifier_groups")
