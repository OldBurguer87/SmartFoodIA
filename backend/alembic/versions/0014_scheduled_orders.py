"""scheduled orders

Revision ID: 0014
Revises: 0013
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "release_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_orders_release_at",
        "orders",
        ["release_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orders_release_at",
        table_name="orders",
    )

    op.drop_column(
        "orders",
        "release_at",
    )

    op.drop_column(
        "orders",
        "scheduled_for",
    )
