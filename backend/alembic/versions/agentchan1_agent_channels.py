"""agent channels: per-agent (Studio) external channels (Telegram)

Revision ID: agentchan1
Revises: foldersync1
Create Date: 2026-06-25

Adds two nullable/defaulted columns to external_platforms so an ExternalPlatform
row can be scoped to a single Studio (agent) and carry an audience policy:
    - studio_id: FK studios.id (nullable) -> when set, this channel belongs to
      one agent instead of the whole org. Indexed for webhook lookups.
    - audience: 'members' | 'anyone' (server_default 'members') -> whether
      inbound users must be verified org members or anyone may chat.

Gated behind HYBRID_AGENT_CHANNELS at the route layer; the columns are inert
(nullable / defaulted) until the feature is on. Dialect-agnostic — works on
both Postgres and SQLite.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "agentchan1"
down_revision: Union[str, None] = "foldersync1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_platforms",
        sa.Column("studio_id", sa.String(length=36), sa.ForeignKey("studios.id"), nullable=True),
    )
    op.add_column(
        "external_platforms",
        sa.Column("audience", sa.String(length=20), nullable=False, server_default="members"),
    )
    op.create_index(
        "ix_external_platforms_studio_id", "external_platforms", ["studio_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_external_platforms_studio_id", table_name="external_platforms")
    op.drop_column("external_platforms", "audience")
    op.drop_column("external_platforms", "studio_id")
