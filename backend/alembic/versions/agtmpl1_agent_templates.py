"""agent templates: create agent_templates

Revision ID: agtmpl1
Revises: chlogseen1
Create Date: 2026-06-25

Creates ``agent_templates`` — shareable, versioned, data-agnostic Studio know-how
(rules, metric formulas, example patterns, skill refs, persona) that others bind
to their own columns. Gated by HYBRID_AGENT_TEMPLATES (default OFF) → table is
inert until the feature is on.

Dialect-agnostic create_table; JSON columns work on both Postgres and SQLite.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "agtmpl1"
down_revision: Union[str, None] = "chlogseen1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain_tags", sa.JSON(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="org"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("author_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("source_studio_id", sa.String(length=36), sa.ForeignKey("studios.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_template_name", "agent_templates", ["name"])
    op.create_index("ix_agent_template_slug", "agent_templates", ["slug"])
    op.create_index("ix_agent_template_scope_status", "agent_templates", ["scope", "status"])
    op.create_index("ix_agent_template_slug_version", "agent_templates", ["slug", "version"])
    op.create_index("ix_agent_template_org", "agent_templates", ["organization_id", "status"])
    op.create_index("ix_agent_template_author", "agent_templates", ["author_user_id"])
    op.create_index("ix_agent_template_source_studio", "agent_templates", ["source_studio_id"])


def downgrade() -> None:
    for ix in (
        "ix_agent_template_source_studio",
        "ix_agent_template_author",
        "ix_agent_template_org",
        "ix_agent_template_slug_version",
        "ix_agent_template_scope_status",
        "ix_agent_template_slug",
        "ix_agent_template_name",
    ):
        op.drop_index(ix, table_name="agent_templates")
    op.drop_table("agent_templates")
