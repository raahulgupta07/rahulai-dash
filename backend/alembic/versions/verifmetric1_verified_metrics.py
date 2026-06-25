"""verified_metrics: add is_locked, last_value, last_value_at to metric_definitions

Revision ID: verifmetric1
Revises: goldenq1
Create Date: 2026-06-25

Additive DDL only — adds three columns to `metric_definitions`:
  * `is_locked`      BOOLEAN NOT NULL DEFAULT false
  * `last_value`     NUMERIC nullable
  * `last_value_at`  TIMESTAMP nullable

When HYBRID_VERIFIED_METRICS is OFF (the default) nothing reads or writes these
columns, so existing deploys are byte-identical.  When the flag is ON and a
metric has is_locked=true, the resolve_metric tool executes sql_calc read-only,
returns the live scalar, and persists the result in last_value/last_value_at.

Dialect-safe (PG + SQLite): the PG-native ``server_default`` 'false' is only
emitted on PostgreSQL; SQLite uses the string '0' literal which SQLAlchemy maps
to boolean False for the BOOLEAN affinity.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "verifmetric1"
down_revision: Union[str, None] = "goldenq1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "metric_definitions"
_IS_PG = lambda: op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    pg = _IS_PG()

    # is_locked — gating column; server_default differs by dialect.
    if pg:
        op.add_column(
            _TABLE,
            sa.Column(
                "is_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    else:
        op.add_column(
            _TABLE,
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="0"),
        )

    # last_value — nullable NUMERIC scalar from the most recent locked execution.
    op.add_column(
        _TABLE,
        sa.Column("last_value", sa.Numeric(), nullable=True),
    )

    # last_value_at — timestamp of the last successful locked execution.
    op.add_column(
        _TABLE,
        sa.Column("last_value_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "last_value_at")
    op.drop_column(_TABLE, "last_value")
    op.drop_column(_TABLE, "is_locked")
