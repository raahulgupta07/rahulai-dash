"""Knowledge graph builder: links semantic tables <-> metrics <-> queries (P8 scaffold).

Gated by flags.SEMANTIC_SEARCH (default OFF).  When OFF returns an empty stats
dict immediately.  When ON it writes lightweight directed edges into the existing
``brain_graph_edges`` table (see app/models/brain_graph_edge.py) so the Phase-8
BrainGraph machinery can traverse them.  If ``brain_graph_edges`` is not suitable
(e.g. schema mismatch), or on any error, this function degrades gracefully and
returns whatever it managed to write, or a stats dict with zeros.

Edge semantics
--------------
* semantic_table  --"has_metric"-->   metric_definition
  (table_name matches the metric's ``data_source_id``'s table, or exact name match)
* metric_definition --"derived_from"-> semantic_table
  (inverse of has_metric, weight lower)
* query_cache       --"answers_about"-> semantic_table
  (proven query's data_source_id matches a semantic table's data_source_id)

All edges are written with ``status='draft'`` and ``source='ai-graph'`` so they
are INVISIBLE to the agent until a human promotes them to 'published' via the
approval gate (same convention as instructions / semantic tables).

Returns a stats dict::

    {
        "tables": int,     # semantic tables scanned
        "metrics": int,    # metric definitions scanned
        "queries": int,    # proven queries scanned
        "edges_written": int,
        "edges_skipped": int,   # already exist (unique constraint)
        "error": str | None,
    }
"""
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)


async def build_knowledge_graph(
    db: Any,
    *,
    org_id: str,
) -> Dict[str, Any]:
    """Build / refresh knowledge graph edges for ``org_id``.

    Fail-soft: any database error is caught, logged, and reflected in the
    returned stats dict.  Never raises.
    """
    from app.settings.hybrid_flags import flags  # local import: stays dep-free

    if not flags.SEMANTIC_SEARCH:
        return {
            "tables": 0,
            "metrics": 0,
            "queries": 0,
            "edges_written": 0,
            "edges_skipped": 0,
            "error": None,
        }

    stats: dict[str, Any] = {
        "tables": 0,
        "metrics": 0,
        "queries": 0,
        "edges_written": 0,
        "edges_skipped": 0,
        "error": None,
    }

    try:
        await _build_edges(db, org_id=org_id, stats=stats)
    except Exception as exc:
        log.warning(
            "build_knowledge_graph: unexpected error for org %s (%s)",
            org_id,
            exc,
            exc_info=True,
        )
        stats["error"] = str(exc)

    return stats


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

async def _build_edges(db: Any, *, org_id: str, stats: dict) -> None:
    """Scan semantic_tables / metric_definitions / query_cache and upsert edges."""
    from sqlalchemy import select, text as sa_text  # noqa: WPS433

    # --- 1. Load semantic tables for this org --------------------------------
    try:
        result = await db.execute(
            sa_text(
                "SELECT id, table_name, data_source_id "
                "FROM semantic_tables "
                "WHERE organization_id = :org_id AND deleted_at IS NULL"
            ),
            {"org_id": org_id},
        )
        sem_tables = result.fetchall()
    except Exception as exc:
        log.debug("build_knowledge_graph: failed to load semantic_tables (%s)", exc)
        sem_tables = []

    stats["tables"] = len(sem_tables)

    # Build lookup: data_source_id -> list of (sem_table_id, table_name)
    ds_to_sem: dict[str, list[tuple[str, str]]] = {}
    for row in sem_tables:
        ds_to_sem.setdefault(row.data_source_id, []).append((row.id, row.table_name))

    # --- 2. Load metric definitions for this org -----------------------------
    try:
        result = await db.execute(
            sa_text(
                "SELECT id, name, data_source_id "
                "FROM metric_definitions "
                "WHERE organization_id = :org_id AND deleted_at IS NULL"
            ),
            {"org_id": org_id},
        )
        metrics = result.fetchall()
    except Exception as exc:
        log.debug("build_knowledge_graph: failed to load metric_definitions (%s)", exc)
        metrics = []

    stats["metrics"] = len(metrics)

    # --- 3. Load proven queries (query_cache, active rows) for this org ------
    try:
        result = await db.execute(
            sa_text(
                "SELECT id, data_source_id, question_norm "
                "FROM query_cache "
                "WHERE organization_id = :org_id "
                "  AND status = 'active' "
                "  AND deleted_at IS NULL"
            ),
            {"org_id": org_id},
        )
        queries = result.fetchall()
    except Exception as exc:
        log.debug("build_knowledge_graph: failed to load query_cache (%s)", exc)
        queries = []

    stats["queries"] = len(queries)

    # --- 4. Write edges ------------------------------------------------------
    # metric --"has_metric"--> semantic_table  (and inverse)
    for metric in metrics:
        ds_id = metric.data_source_id
        for sem_id, _tname in ds_to_sem.get(ds_id or "", []):
            await _upsert_edge(
                db,
                org_id=org_id,
                src_entity=f"metric:{metric.id}",
                dst_entity=f"table:{sem_id}",
                relation="derived_from",
                weight=0.7,
                stats=stats,
            )
            await _upsert_edge(
                db,
                org_id=org_id,
                src_entity=f"table:{sem_id}",
                dst_entity=f"metric:{metric.id}",
                relation="has_metric",
                weight=0.8,
                stats=stats,
            )

    # query --"answers_about"--> semantic_table
    for query in queries:
        ds_id = query.data_source_id
        for sem_id, _tname in ds_to_sem.get(ds_id or "", []):
            await _upsert_edge(
                db,
                org_id=org_id,
                src_entity=f"query:{query.id}",
                dst_entity=f"table:{sem_id}",
                relation="answers_about",
                weight=0.6,
                stats=stats,
            )


async def _upsert_edge(
    db: Any,
    *,
    org_id: str,
    src_entity: str,
    dst_entity: str,
    relation: str,
    weight: float,
    stats: dict,
) -> None:
    """Insert a draft edge into brain_graph_edges, ignoring unique conflicts.

    brain_graph_edges has a unique constraint on
    (organization_id, data_source_id, src_entity, dst_entity, relation).
    Here data_source_id is NULL (these are org-level cross-entity edges, not
    single-DS edges).  Conflicts are silently swallowed.
    """
    from sqlalchemy import text as sa_text  # noqa: WPS433
    import uuid as _uuid

    insert_sql = sa_text(
        """
        INSERT INTO brain_graph_edges
            (id, organization_id, data_source_id,
             src_entity, dst_entity, relation, weight,
             status, source,
             created_at, updated_at)
        VALUES
            (:id, :org_id, NULL,
             :src, :dst, :rel, :weight,
             'draft', 'ai-graph',
             NOW(), NOW())
        ON CONFLICT DO NOTHING
        """
    )
    try:
        result = await db.execute(
            insert_sql,
            {
                "id": str(_uuid.uuid4()),
                "org_id": org_id,
                "src": src_entity,
                "dst": dst_entity,
                "rel": relation,
                "weight": weight,
            },
        )
        # rowcount == 1 if inserted, 0 if skipped (ON CONFLICT DO NOTHING)
        inserted = getattr(result, "rowcount", 1)
        if inserted:
            stats["edges_written"] += 1
        else:
            stats["edges_skipped"] += 1
    except Exception as exc:
        log.debug(
            "_upsert_edge: skipping (%s -> %s via %s): %s",
            src_entity, dst_entity, relation, exc,
        )
        stats["edges_skipped"] += 1
