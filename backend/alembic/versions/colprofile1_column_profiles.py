"""column_profiles: F09 Ingest Brain per-column profile table

Revision ID: colprofile1
Revises: sessumm1
Create Date: 2026-06-29

ROADMAP F09 (Universal Ingest Brain), Phase 1. Stores the durable per-column
understanding produced by the PROFILE/UNDERSTAND/UNIFY stages: dtype, unit,
null%, cardinality, PII flag, semantic role, synonyms, LLM meaning, and the
cross-source ``maps_to`` link. Review-gated (status pending→approved).

No FK constraints by design (enrichment/tracking table — avoids delete-cascade
coupling, same convention as ingest_batches). PG-guarded; idempotent.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "colprofile1"
down_revision: Union[str, None] = "sessumm1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # PG-only feature path; SQLite test DBs skip

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS column_profiles (
            id                   VARCHAR(36) PRIMARY KEY,
            organization_id      VARCHAR(36) NOT NULL,
            data_source_id       VARCHAR(36),
            connection_table_id  VARCHAR(36),
            table_name           VARCHAR,
            column_name          VARCHAR NOT NULL,
            normalized_name      VARCHAR,
            dtype                VARCHAR(16),
            unit                 VARCHAR(32),
            null_pct             DOUBLE PRECISION NOT NULL DEFAULT 0,
            cardinality          INTEGER NOT NULL DEFAULT 0,
            sample_values        JSON,
            pii_flag             BOOLEAN NOT NULL DEFAULT false,
            semantic_role        VARCHAR(16),
            synonyms             JSON,
            meaning              VARCHAR,
            maps_to              VARCHAR,
            source_ref           JSON,
            status               VARCHAR(16) NOT NULL DEFAULT 'pending',
            created_at           TIMESTAMP,
            updated_at           TIMESTAMP,
            deleted_at           TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_column_profiles_org ON column_profiles (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_column_profiles_org_ds ON column_profiles (organization_id, data_source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_column_profiles_table ON column_profiles (data_source_id, table_name)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS column_profiles")
