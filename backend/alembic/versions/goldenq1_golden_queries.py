"""golden_queries: add is_golden + verified_count to query_library_items

Revision ID: goldenq1
Revises: resultcache1
Create Date: 2026-06-25

Additive DDL only — adds two columns to `query_library_items`:
  * `is_golden`      BOOLEAN NOT NULL DEFAULT false
  * `verified_count` INTEGER NOT NULL DEFAULT 0

Both default to the falsy value so all existing rows are unaffected.
Behaviour is inert unless flags.GOLDEN_QUERIES is ON — nothing reads or
writes these columns when the flag is off. Dialect-safe (PG + SQLite):
SQLite does not support server_default expressions via ALTER ADD COLUMN for
booleans, so we only emit the PG-native server_default on PostgreSQL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "goldenq1"
down_revision: Union[str, None] = "resultcache1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "query_library_items"
_IS_PG = lambda: op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    pg = _IS_PG()

    # is_golden — Boolean column (PG: with server_default; SQLite: no server_default
    # because SQLite ALTER ADD COLUMN only supports literal constants for NOT NULL cols
    # and SQLAlchemy emits BOOLEAN which SQLite handles fine with Python-side default).
    if pg:
        op.add_column(
            _TABLE,
            sa.Column(
                "is_golden",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    else:
        op.add_column(
            _TABLE,
            sa.Column("is_golden", sa.Boolean(), nullable=False, server_default="0"),
        )

    # verified_count — Integer column tracking how many times this query has been
    # positively confirmed (thumbs-up or successful re-use).
    op.add_column(
        _TABLE,
        sa.Column(
            "verified_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "verified_count")
    op.drop_column(_TABLE, "is_golden")
