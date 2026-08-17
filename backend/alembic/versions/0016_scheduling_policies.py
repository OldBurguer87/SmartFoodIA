"""scheduling policies

Revision ID: 0016
Revises: 0015
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "allow_scheduled_orders",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "allow_scheduled_when_closed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "scheduled_min_notice_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "store_commercial_rules",
        sa.Column(
            "scheduled_max_days_ahead",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "store_commercial_rules",
        "scheduled_max_days_ahead",
    )

    op.drop_column(
        "store_commercial_rules",
        "scheduled_min_notice_minutes",
    )

    op.drop_column(
        "store_commercial_rules",
        "allow_scheduled_when_closed",
    )

    op.drop_column(
        "store_commercial_rules",
        "allow_scheduled_orders",
    )
