"""SQLAlchemy model for the knowledge_search_index table.

Introduced in migration hybridsearch1.  Maps the base columns only — the
PostgreSQL-specific ``tsv`` (tsvector) and ``embedding`` (vector) columns are
added by the migration via raw DDL and are intentionally NOT mapped here so the
model remains SQLite-safe for unit / dev environments.  When HYBRID_SEMANTIC_SEARCH
is ON, the PG full-text and (future) vector columns are accessed via raw SQL in
``app/ai/knowledge/hybrid_search.py``.

One row per indexed knowledge asset:
    kind='table'   -> ref_id = semantic_tables.id
    kind='metric'  -> ref_id = metric_definitions.id
    kind='query'   -> ref_id = query_cache.id (or query_library item)
    kind='doc'     -> ref_id = knowledge_docs.id
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, String, Text

from app.models.base import BaseSchema


class KnowledgeSearchIndex(BaseSchema):
    """Unified full-text search index over org knowledge assets (P8 scaffold).

    Default-OFF — gated by flags.SEMANTIC_SEARCH.  The table exists in PG but
    is never written/read until the flag is enabled.  Additive: does not touch
    any existing table.
    """

    __tablename__ = "knowledge_search_index"
    __table_args__ = (
        Index("ix_ksi_org_id", "org_id"),
        Index("ix_ksi_org_kind", "org_id", "kind"),
    )

    # Owning org
    org_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Asset category: 'table' | 'metric' | 'query' | 'doc'
    kind = Column(String(20), nullable=False)

    # FK into the source table (semantic_tables.id, metric_definitions.id, …).
    # Nullable because some future kinds may not have a single source table.
    ref_id = Column(String(36), nullable=True)

    # Human-readable label (table name, metric name, question text, doc title)
    title = Column(Text, nullable=False, default="")

    # Full searchable content — concatenation of relevant fields from the source
    # row (description, SQL template, body, etc.).  Used to populate ``tsv`` and
    # as the token-Jaccard corpus when PG FTS is unavailable.
    body = Column(Text, nullable=False, default="")

    # NOTE: ``tsv`` (tsvector) and ``embedding`` (vector(1536)) columns exist in
    # Postgres but are NOT declared here — see migration hybridsearch1 and
    # hybrid_search.py for raw-SQL access patterns.

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeSearchIndex kind={self.kind!r} ref_id={self.ref_id!r}>"
