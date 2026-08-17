"""multi company authentication

Revision ID: 0015
Revises: 0014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
    )

    op.create_table(
        "company_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.String(30),
            nullable=False,
            server_default="MANAGER",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
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
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "user_id",
            name="uq_company_users_company_user",
        ),
    )

    op.create_index(
        "ix_company_users_company_id",
        "company_users",
        ["company_id"],
    )

    op.create_index(
        "ix_company_users_user_id",
        "company_users",
        ["user_id"],
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "token_hash",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
        ),
        sa.Column(
            "user_agent",
            sa.String(500),
        ),
        sa.Column(
            "ip_address",
            sa.String(64),
        ),
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
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_index(
        "ix_auth_sessions_user_id",
        "auth_sessions",
        ["user_id"],
    )

    op.create_index(
        "ix_auth_sessions_token_hash",
        "auth_sessions",
        ["token_hash"],
    )

    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_sessions_expires_at",
        table_name="auth_sessions",
    )
    op.drop_index(
        "ix_auth_sessions_token_hash",
        table_name="auth_sessions",
    )
    op.drop_index(
        "ix_auth_sessions_user_id",
        table_name="auth_sessions",
    )
    op.drop_table("auth_sessions")

    op.drop_index(
        "ix_company_users_user_id",
        table_name="company_users",
    )
    op.drop_index(
        "ix_company_users_company_id",
        table_name="company_users",
    )
    op.drop_table("company_users")

    op.drop_index(
        "ix_users_email",
        table_name="users",
    )
    op.drop_table("users")
