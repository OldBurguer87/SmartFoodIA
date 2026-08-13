"""Add per-store commercial rules, schedules, delivery zones and menu PDFs.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_commercial_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("manual_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pause_reason", sa.String(length=240), nullable=True),
        sa.Column("delivery_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("takeout_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("minimum_delivery_subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("delivery_fee_mode", sa.String(length=20), nullable=False, server_default="FIXED"),
        sa.Column("fixed_delivery_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("accepts_pix", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("accepts_credit", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("accepts_debit", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("accepts_cash", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_change", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("average_prep_minutes", sa.Integer(), nullable=True),
        sa.Column("general_notes", sa.Text(), nullable=True),
        sa.Column("menu_original_name", sa.String(length=240), nullable=True),
        sa.Column("menu_storage_name", sa.String(length=240), nullable=True),
        sa.Column("menu_public_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", name="uq_store_commercial_rules_store"),
        sa.UniqueConstraint("menu_public_token"),
    )

    op.create_table(
        "store_business_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("delivery_until", sa.Time(), nullable=True),
        sa.Column("takeout_until", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "weekday", name="uq_store_business_hours_day"),
    )

    op.create_table(
        "store_delivery_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("normalized_name", sa.String(length=140), nullable=False),
        sa.Column("fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("delivery_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "normalized_name", name="uq_store_delivery_zone_name"),
    )

    op.create_table(
        "store_menu_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("original_name", sa.String(length=240), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False, server_default="application/pdf"),
        sa.Column("public_token", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", name="uq_store_menu_document_store"),
        sa.UniqueConstraint("public_token"),
    )


def downgrade() -> None:
    op.drop_table("store_menu_documents")
    op.drop_table("store_delivery_zones")
    op.drop_table("store_business_hours")
    op.drop_table("store_commercial_rules")
