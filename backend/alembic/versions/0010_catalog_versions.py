"""Add catalog source configuration, versions and source files.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_catalog_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=40),
            nullable=False,
            server_default="GENERIC",
        ),
        sa.Column("products_source", sa.String(length=30), nullable=True),
        sa.Column("complements_source", sa.String(length=30), nullable=True),
        sa.Column("relations_source", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            name="uq_store_catalog_config_store",
        ),
    )

    op.create_table(
        "catalog_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("version_code", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "products_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "modifiers_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "relations_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "version_code",
            name="uq_catalog_version_store_code",
        ),
    )

    op.create_index(
        "ix_catalog_versions_store_id",
        "catalog_versions",
        ["store_id"],
    )

    op.create_table(
        "catalog_source_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("source_format", sa.String(length=20), nullable=False),
        sa.Column("original_name", sa.String(length=240), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_version_id"],
            ["catalog_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_version_id",
            "role",
            name="uq_catalog_source_file_version_role",
        ),
    )

    op.create_index(
        "ix_catalog_source_files_store_id",
        "catalog_source_files",
        ["store_id"],
    )

    op.create_index(
        "ix_catalog_source_files_catalog_version_id",
        "catalog_source_files",
        ["catalog_version_id"],
    )

    op.add_column(
        "store_menu_documents",
        sa.Column(
            "catalog_version_id",
            sa.Uuid(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_store_menu_document_catalog_version",
        "store_menu_documents",
        "catalog_versions",
        ["catalog_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_store_menu_documents_catalog_version_id",
        "store_menu_documents",
        ["catalog_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_store_menu_documents_catalog_version_id",
        table_name="store_menu_documents",
    )

    op.drop_constraint(
        "fk_store_menu_document_catalog_version",
        "store_menu_documents",
        type_="foreignkey",
    )

    op.drop_column(
        "store_menu_documents",
        "catalog_version_id",
    )

    op.drop_index(
        "ix_catalog_source_files_catalog_version_id",
        table_name="catalog_source_files",
    )

    op.drop_index(
        "ix_catalog_source_files_store_id",
        table_name="catalog_source_files",
    )

    op.drop_table("catalog_source_files")

    op.drop_index(
        "ix_catalog_versions_store_id",
        table_name="catalog_versions",
    )

    op.drop_table("catalog_versions")
    op.drop_table("store_catalog_configs")
