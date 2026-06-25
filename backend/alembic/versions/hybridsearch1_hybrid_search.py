"""hybrid search + knowledge graph scaffold: knowledge_search_index table

Revision ID: hybridsearch1
Revises: verifmetric1
Create Date: 2026-06-25

Phase P8 scaffolding — creates `knowledge_search_index`, a unified full-text
search + future pgvector index over knowledge assets (semantic tables, metrics,
proven queries, knowledge docs).

Schema:
    id            UUID PK
    org_id        FK organizations.id (with index)
    kind          'table' | 'metric' | 'query' | 'doc'
    ref_id        FK into the source row (nullable — doc may not yet be in a
                  single table)
    title         text — short label (table name, metric name, question …)
    body          text — full searchable content
    tsv           tsvector — PG full-text search vector (GIN indexed, PG-only)
    embedding     vector(1536) — future-proofing, always NULL for now

All PG-specific DDL (tsvector column, GIN index, vector column) is guarded
on op.get_bind().dialect.name == 'postgresql' so SQLite unit-test migrations
still run cleanly.

When HYBRID_SEMANTIC_SEARCH is OFF (the default) nothing reads or writes this
table, so existing deploys are byte-identical.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "hybridsearch1"
down_revision: Union[str, None] = "verifmetric1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Base columns (dialect-agnostic) ------------------------------------
    op.create_table(
        "knowledge_search_index",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # kind: 'table' | 'metric' | 'query' | 'doc'
        sa.Column("kind", sa.String(length=20), nullable=False),
        # ref_id: id in the source table (semantic_tables, metric_definitions, …)
        sa.Column("ref_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )

    # Standard BTree indexes (all dialects)
    op.create_index("ix_ksi_id", "knowledge_search_index", ["id"])
    op.create_index("ix_ksi_org_id", "knowledge_search_index", ["org_id"])
    op.create_index("ix_ksi_org_kind", "knowledge_search_index", ["org_id", "kind"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # tsvector column (computed at insert/update time by a trigger or explicit
        # to_tsvector() call; stored to avoid recompute on every query).
        op.execute(
            "ALTER TABLE knowledge_search_index "
            "ADD COLUMN IF NOT EXISTS tsv tsvector"
        )
        # GIN index on tsvector for fast full-text queries
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_ksi_tsv "
            "ON knowledge_search_index USING gin (tsv)"
        )
        # Future-proof pgvector column (1536 dims = text-embedding-3-small).
        # Left NULL for now — no embedder in the image today. Never queried
        # while HYBRID_SEMANTIC_SEARCH is OFF.
        op.execute(
            "ALTER TABLE knowledge_search_index "
            "ADD COLUMN IF NOT EXISTS embedding vector(1536)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_ksi_tsv")
    op.drop_table("knowledge_search_index")
