"""order payments and mixed payment support

Revision ID: 0024
Revises: 0023
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_payments",
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "method",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "payment_type",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "change_for",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
        sa.Column(
            "position",
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
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "method",
            name="uq_order_payment_method",
        ),
        sa.UniqueConstraint(
            "order_id",
            "position",
            name="uq_order_payment_position",
        ),
    )

    op.create_index(
        "ix_order_payments_order_id",
        "order_payments",
        ["order_id"],
        unique=False,
    )

    op.create_index(
        "ix_order_payments_method",
        "order_payments",
        ["method"],
        unique=False,
    )

    # Backfill de todos os pedidos antigos.
    # Cada pedido existente passa a ter exatamente uma parcela,
    # reproduzindo seu pagamento atual.
    op.execute(
        """
        INSERT INTO order_payments (
            id,
            order_id,
            method,
            payment_type,
            amount,
            change_for,
            position,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            id,
            payment_method,
            payment_type,
            total,
            change_for,
            1,
            created_at,
            updated_at
        FROM orders
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_payments_method",
        table_name="order_payments",
    )
    op.drop_index(
        "ix_order_payments_order_id",
        table_name="order_payments",
    )
    op.drop_table("order_payments")
