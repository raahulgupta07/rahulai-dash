"""result_cache_entries: Task 7 deterministic create_data result cache

Revision ID: resultcache1
Revises: packwin1
Create Date: 2026-06-24

One additive table backing the HYBRID_RESULT_CACHE flag. A row is a stored
create_data result keyed by a SHA-256 of (normalized question text + the
report's per-source row-count *watermark signature*). On a cache HIT with an
unchanged watermark we serve `result_json` and skip codegen + execution; a
re-train / new upload bumps the watermark so the key changes and the entry
naturally misses (rebuild once). Inert unless flags.RESULT_CACHE — nothing
reads/writes this table on existing deploys. Dialect-safe (PG + SQLite).
down_revision chains off the single head `packwin1`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "resultcache1"
down_revision: Union[str, None] = "packwin1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "result_cache_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("question_norm", sa.Text(), nullable=False, server_default=""),
        sa.Column("watermark_sig", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_result_cache_entries_id"), "result_cache_entries",
                    ["id"], unique=True)
    op.create_index(op.f("ix_result_cache_entries_organization_id"),
                    "result_cache_entries", ["organization_id"], unique=False)
    op.create_index(op.f("ix_result_cache_entries_report_id"),
                    "result_cache_entries", ["report_id"], unique=False)
    op.create_index(op.f("ix_result_cache_entries_cache_key"),
                    "result_cache_entries", ["cache_key"], unique=False)
    op.create_index("ix_result_cache_lookup", "result_cache_entries",
                    ["organization_id", "cache_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_result_cache_lookup", table_name="result_cache_entries")
    op.drop_index(op.f("ix_result_cache_entries_cache_key"),
                  table_name="result_cache_entries")
    op.drop_index(op.f("ix_result_cache_entries_report_id"),
                  table_name="result_cache_entries")
    op.drop_index(op.f("ix_result_cache_entries_organization_id"),
                  table_name="result_cache_entries")
    op.drop_index(op.f("ix_result_cache_entries_id"),
                  table_name="result_cache_entries")
    op.drop_table("result_cache_entries")
