"""store operation mode

Revision ID: 0020
Revises: 0019
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column(
            "operation_mode",
            sa.String(length=20),
            nullable=False,
            server_default="OLIVIA",
        ),
    )


def downgrade() -> None:
    op.drop_column("stores", "operation_mode")
