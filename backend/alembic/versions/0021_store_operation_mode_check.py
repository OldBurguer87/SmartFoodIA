"""store operation mode check constraint

Revision ID: 0021
Revises: 0020
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_stores_operation_mode",
        "stores",
        "operation_mode IN ('OLIVIA', 'HUMAN_ONLY')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_stores_operation_mode",
        "stores",
        type_="check",
    )
