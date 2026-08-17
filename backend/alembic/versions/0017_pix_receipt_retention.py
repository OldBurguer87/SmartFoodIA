"""pix receipt retention

Revision ID: 0017
Revises: 0016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "payment_receipts",
        "storage_path",
        existing_type=sa.String(length=500),
        nullable=True,
    )

    op.alter_column(
        "payment_receipts",
        "external_media_id",
        existing_type=sa.String(length=180),
        nullable=True,
    )

    op.add_column(
        "payment_receipts",
        sa.Column(
            "transaction_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "payment_receipts",
        sa.Column(
            "retention_purged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_payment_receipts_transaction_fingerprint",
        "payment_receipts",
        ["transaction_fingerprint"],
    )

    op.create_index(
        "ix_payment_receipts_retention_purged_at",
        "payment_receipts",
        ["retention_purged_at"],
    )


def downgrade() -> None:
    op.execute(
        "UPDATE payment_receipts "
        "SET external_media_id = '' "
        "WHERE external_media_id IS NULL"
    )

    op.execute(
        "UPDATE payment_receipts "
        "SET storage_path = '' "
        "WHERE storage_path IS NULL"
    )

    op.drop_index(
        "ix_payment_receipts_retention_purged_at",
        table_name="payment_receipts",
    )

    op.drop_index(
        "ix_payment_receipts_transaction_fingerprint",
        table_name="payment_receipts",
    )

    op.drop_column(
        "payment_receipts",
        "retention_purged_at",
    )

    op.drop_column(
        "payment_receipts",
        "transaction_fingerprint",
    )

    op.alter_column(
        "payment_receipts",
        "external_media_id",
        existing_type=sa.String(length=180),
        nullable=False,
    )

    op.alter_column(
        "payment_receipts",
        "storage_path",
        existing_type=sa.String(length=500),
        nullable=False,
    )
