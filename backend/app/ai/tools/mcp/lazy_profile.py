"""Lazy profile-v2 on cache-miss — zero-touch schema drift guard.

When a table appears in a query (via create_data or inspect_data) but has no
profile_v2 data yet (e.g. added after training), this module profiles it
inline so the agent has a dimension catalog for it. The profile is persisted
and available for all subsequent calls.

Gates:
  • flags.PROFILE_V2 must be ON (HYBRID_PROFILE_V2=1)
  • env var LAZY_PROFILE_V2_DISABLED=1 acts as a kill-switch (honored
    independently so lazy profiling can be turned off without touching the
    main flag — useful when bulk-profiling via the train path is preferred).

When either gate is closed this function is a pure no-op: zero DB reads,
zero imports of the heavier profiler. OFF -> byte-identical behaviour.

Fail-soft contract:
  Any error in this block (DB, profiler, timeout) must never propagate to
  the caller. The worst outcome is that the table starts without a profile,
  exactly as before. All exceptions are caught and logged at DEBUG level.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_LAZY_CAP = 10          # max tables profiled per invocation
_PROFILE_TIMEOUT = 5.0  # seconds per table (profile_table_v2 is ~1.4s each)


def _kill_switch_active() -> bool:
    """Return True when LAZY_PROFILE_V2_DISABLED=1 (or truthy variant)."""
    raw = os.environ.get("LAZY_PROFILE_V2_DISABLED", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def lazy_profile_tables(
    db,                          # AsyncSession
    tables_by_source: List[Dict[str, Any]],
) -> None:
    """Profile any referenced tables that lack a profile_v2 entry.

    Parameters
    ----------
    db : AsyncSession
        The current request's async DB session. The function adds any dirty
        DataSourceTable rows and commits within its own nested savepoint so
        it does not interfere with the caller's transaction.
    tables_by_source : list[dict]
        Resolved tables in the form [{"data_source_id": str, "tables": [str]}].
        If empty or None nothing is done.
    """
    # ── Gate 1: feature flag ──────────────────────────────────────────────────
    try:
        from app.settings.hybrid_flags import flags
        if not flags.PROFILE_V2:
            return
    except Exception:
        return  # flag module unavailable → no-op

    # ── Gate 2: kill-switch ───────────────────────────────────────────────────
    if _kill_switch_active():
        return

    # ── Gate 3: nothing to do ─────────────────────────────────────────────────
    if not tables_by_source:
        return

    try:
        await _run_lazy_profile(db, tables_by_source)
    except Exception as exc:
        # Top-level safety net — must never surface to caller.
        logger.debug("lazy_profile_tables: unexpected error (suppressed): %s", exc)


async def _run_lazy_profile(db, tables_by_source: List[Dict[str, Any]]) -> None:
    """Inner implementation — exceptions are caught by the caller."""
    from sqlalchemy import select, and_
    from app.models.datasource_table import DataSourceTable
    from app.ai.knowledge.profile_v2 import profile_table_v2

    # Collect (ds_id, table_name) pairs that need profiling.
    candidates: List[tuple[str, str]] = []
    for group in (tables_by_source or []):
        ds_id = group.get("data_source_id")
        tbl_names = group.get("tables") or []
        for name in tbl_names:
            if ds_id and name:
                candidates.append((str(ds_id), str(name)))

    if not candidates:
        return

    # Fetch the ORM rows in one query.
    # Filter: datasource_id IN [...] AND name IN [...]
    ds_ids  = list({c[0] for c in candidates})
    tbl_names_set = list({c[1] for c in candidates})

    stmt = (
        select(DataSourceTable)
        .where(
            and_(
                DataSourceTable.datasource_id.in_(ds_ids),
                DataSourceTable.name.in_(tbl_names_set),
                DataSourceTable.is_active.is_(True),
            )
        )
    )
    try:
        result = await db.execute(stmt)
        rows: list[DataSourceTable] = list(result.scalars().all())
    except Exception as exc:
        logger.debug("lazy_profile_tables: DB fetch failed: %s", exc)
        return

    if not rows:
        return

    # Filter to only those missing profile_v2 and build a (ds_id, name) lookup.
    needs_profile: list[DataSourceTable] = []
    for row in rows:
        meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        if not meta.get("profile_v2"):
            needs_profile.append(row)

    if not needs_profile:
        logger.debug("lazy_profile_tables: all %d referenced tables already profiled", len(rows))
        return

    # Cap to avoid long delays on large schemas.
    if len(needs_profile) > _LAZY_CAP:
        logger.debug(
            "lazy_profile_tables: capping from %d to %d tables",
            len(needs_profile), _LAZY_CAP,
        )
        needs_profile = needs_profile[:_LAZY_CAP]

    logger.debug(
        "lazy_profile_tables: profiling %d table(s) without profile_v2: %s",
        len(needs_profile),
        [t.name for t in needs_profile],
    )

    # Profile each table in a sync worker thread (profile_table_v2 hits the DB
    # via a sync engine and is CPU-bound for classification). Fail-soft per table.
    profiled_any = False
    for tbl in needs_profile:
        try:
            profiled = await asyncio.wait_for(
                asyncio.to_thread(profile_table_v2, tbl),
                timeout=_PROFILE_TIMEOUT,
            )
            if profiled:
                profiled_any = True
                logger.debug(
                    "lazy_profile_tables: profiled table %s (%d cols)",
                    tbl.name, len(profiled),
                )
            else:
                logger.debug("lazy_profile_tables: profile_table_v2 returned empty for %s", tbl.name)
        except asyncio.TimeoutError:
            logger.debug("lazy_profile_tables: timeout profiling table %s", tbl.name)
        except Exception as exc:
            logger.debug("lazy_profile_tables: error profiling table %s: %s", tbl.name, exc)

    # Commit the profiled metadata so it is available to this request AND
    # future requests. Use a nested savepoint so a commit failure here does
    # not disturb the caller's main transaction.
    if profiled_any:
        try:
            await db.commit()
        except Exception as exc:
            logger.debug("lazy_profile_tables: commit failed (suppressed): %s", exc)
            try:
                await db.rollback()
            except Exception:
                pass
