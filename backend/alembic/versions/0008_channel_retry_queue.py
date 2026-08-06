"""Add channel retry scheduling fields.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("channel_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("channel_events", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbound_channel_messages", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbound_channel_messages", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_channel_events_queue", "channel_events", ["status", "next_attempt_at"], unique=False)
    op.create_index("ix_outbound_messages_queue", "outbound_channel_messages", ["status", "next_attempt_at"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_outbound_messages_queue", table_name="outbound_channel_messages")
    op.drop_index("ix_channel_events_queue", table_name="channel_events")
    op.drop_column("outbound_channel_messages", "sent_at")
    op.drop_column("outbound_channel_messages", "next_attempt_at")
    op.drop_column("channel_events", "processed_at")
    op.drop_column("channel_events", "next_attempt_at")
