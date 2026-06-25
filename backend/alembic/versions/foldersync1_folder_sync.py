"""folder sync: create folder_sync_states

Revision ID: foldersync1
Revises: agtmpl1
Create Date: 2026-06-25

Server-side delta ledger for the desktop Folder Sync agent (HYBRID_FOLDER_SYNC,
default OFF). One row per (org, local path): last synced sha256 + the DataSource /
Studio it resolved to, so re-pushes are no-ops and edits replace the same agent.
Table is inert until the feature is on.

Dialect-agnostic create_table; works on both Postgres and SQLite.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "foldersync1"
down_revision: Union[str, None] = "agtmpl1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "folder_sync_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("machine_label", sa.String(length=255), nullable=True),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("data_source_id", sa.String(length=36), nullable=True),
        sa.Column("studio_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_folder_sync_states_organization_id", "folder_sync_states", ["organization_id"])
    op.create_index("ix_folder_sync_states_user_id", "folder_sync_states", ["user_id"])
    op.create_index("ix_folder_sync_org_path", "folder_sync_states", ["organization_id", "source_path"], unique=True)
    op.create_index("ix_folder_sync_org_machine", "folder_sync_states", ["organization_id", "machine_label"])


def downgrade() -> None:
    for ix in (
        "ix_folder_sync_org_machine",
        "ix_folder_sync_org_path",
        "ix_folder_sync_states_user_id",
        "ix_folder_sync_states_organization_id",
    ):
        op.drop_index(ix, table_name="folder_sync_states")
    op.drop_table("folder_sync_states")
