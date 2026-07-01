"""data_sources: per-user connector template columns

Revision ID: peruser_tmpl1
Revises: ratiodef1
Create Date: 2026-07-01

Per-user private connector. An admin marks a DataSource as a TEMPLATE
(is_user_template=True) — a config shell with tenant/client but no user creds and
no synced data. Each member registers against it with their own credentials,
cloning it into a private, owner-scoped DataSource (template_source_id → the
template) with their own catalog. See services/per_user_connector.py.

Additive, idempotent (IF NOT EXISTS), PG-guarded.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "peruser_tmpl1"
down_revision: Union[str, None] = "ratiodef1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE data_sources
            ADD COLUMN IF NOT EXISTS is_user_template boolean NOT NULL DEFAULT false;
        ALTER TABLE data_sources
            ADD COLUMN IF NOT EXISTS template_source_id varchar(36);
        """
    )
    # FK is best-effort (skip if it already exists)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_data_sources_template_source'
            ) THEN
                ALTER TABLE data_sources
                    ADD CONSTRAINT fk_data_sources_template_source
                    FOREIGN KEY (template_source_id) REFERENCES data_sources(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE data_sources DROP CONSTRAINT IF EXISTS fk_data_sources_template_source;
        ALTER TABLE data_sources DROP COLUMN IF EXISTS template_source_id;
        ALTER TABLE data_sources DROP COLUMN IF EXISTS is_user_template;
        """
    )
