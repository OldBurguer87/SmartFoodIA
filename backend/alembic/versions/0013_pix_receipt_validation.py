"""Add PIX receipt validation.

Revision ID: 0013
Revises: 0012
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "store_commercial_rules",
        sa.Column("pix_receiver_name", sa.String(length=180)),
    )
    op.add_column(
        "store_commercial_rules",
        sa.Column("pix_receiver_document", sa.String(length=40)),
    )
    op.add_column(
        "store_commercial_rules",
        sa.Column("pix_key", sa.String(length=200)),
    )
    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "pix_receiver_institution",
            sa.String(length=180),
        ),
    )
    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "pix_auto_verify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "pix_receipt_max_age_minutes",
            sa.Integer(),
            nullable=False,
            server_default="360",
        ),
    )
    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "pix_amount_tolerance",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.01",
        ),
    )

    op.create_table(
        "payment_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid()),
        sa.Column("channel_event_id", sa.Uuid()),
        sa.Column("external_media_id", sa.String(length=180), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=120)),
        sa.Column("original_filename", sa.String(length=240)),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="RECEIVED",
        ),
        sa.Column("extracted_receiver_name", sa.String(length=180)),
        sa.Column("extracted_receiver_document", sa.String(length=40)),
        sa.Column("extracted_pix_key", sa.String(length=200)),
        sa.Column("extracted_amount", sa.Numeric(12, 2)),
        sa.Column("extracted_paid_at", sa.DateTime(timezone=True)),
        sa.Column("extracted_transaction_id", sa.String(length=200)),
        sa.Column("extracted_transaction_status", sa.String(length=100)),
        sa.Column("extracted_payer_name", sa.String(length=180)),
        sa.Column("extracted_institution", sa.String(length=180)),
        sa.Column("ai_confidence", sa.Numeric(5, 4)),
        sa.Column("validation_json", sa.JSON()),
        sa.Column("reviewed_by", sa.String(length=160)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text()),
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
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["channel_event_id"],
            ["channel_events.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_event_id"),
    )

    op.create_index(
        "ix_payment_receipts_store_id",
        "payment_receipts",
        ["store_id"],
    )
    op.create_index(
        "ix_payment_receipts_order_id",
        "payment_receipts",
        ["order_id"],
    )
    op.create_index(
        "ix_payment_receipts_conversation_id",
        "payment_receipts",
        ["conversation_id"],
    )
    op.create_index(
        "ix_payment_receipts_file_sha256",
        "payment_receipts",
        ["file_sha256"],
    )
    op.create_index(
        "ix_payment_receipts_status",
        "payment_receipts",
        ["status"],
    )
    op.create_index(
        "ix_payment_receipts_transaction_id",
        "payment_receipts",
        ["extracted_transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_receipts_transaction_id",
        table_name="payment_receipts",
    )
    op.drop_index(
        "ix_payment_receipts_status",
        table_name="payment_receipts",
    )
    op.drop_index(
        "ix_payment_receipts_file_sha256",
        table_name="payment_receipts",
    )
    op.drop_index(
        "ix_payment_receipts_conversation_id",
        table_name="payment_receipts",
    )
    op.drop_index(
        "ix_payment_receipts_order_id",
        table_name="payment_receipts",
    )
    op.drop_index(
        "ix_payment_receipts_store_id",
        table_name="payment_receipts",
    )

    op.drop_table("payment_receipts")

    op.drop_column(
        "store_commercial_rules",
        "pix_amount_tolerance",
    )
    op.drop_column(
        "store_commercial_rules",
        "pix_receipt_max_age_minutes",
    )
    op.drop_column(
        "store_commercial_rules",
        "pix_auto_verify_enabled",
    )
    op.drop_column(
        "store_commercial_rules",
        "pix_receiver_institution",
    )
    op.drop_column(
        "store_commercial_rules",
        "pix_key",
    )
    op.drop_column(
        "store_commercial_rules",
        "pix_receiver_document",
    )
    op.drop_column(
        "store_commercial_rules",
        "pix_receiver_name",
    )
