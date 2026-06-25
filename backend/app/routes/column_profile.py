"""Column Intelligence routes (Batch B / Phase 3) — pre-train per-column profile.

  POST /api/data_sources/{data_source_id}/profile
       body (optional): {"table_name": "..."}
       -> runs the read-only column profiler and MERGES the result into each
          matched ``DataSourceTable.columns[].metadata`` (role, values, distinct,
          null_pct, min, max) WITHOUT touching existing ``description`` or any
          manually-set metadata key. Returns the profile + write counts.

  GET  /api/data_sources/{data_source_id}/columns/intel
       -> returns the currently-stored per-column intel (name, dtype,
          description, role, values, distinct, null_pct) for the UI / review.

Every aggregation runs through ``DataSource.get_client().aexecute_query`` (live
DuckDB for the spreadsheet connector) — same path as the compliance scanner.
The agent reads ``metadata.role`` + ``metadata.values`` straight out of the
schema XML (tables_schema_section), so once this writes, the agent is expert on
the columns BEFORE the first question — no question-time discovery.

Gated behind ``flags.COLUMN_INTEL`` (NEW flag). Returns 200 {disabled:True}
when off so the UI hides it cleanly.

NOTE: deliberately NO `from __future__ import annotations` (body+permission
route landmine: stringized annotations make FastAPI mis-read the pydantic body
as a query param).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.dependencies import get_async_db, get_current_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.data_source import DataSource
from app.models.datasource_table import DataSourceTable
from app.core.auth import current_user
from app.core.permissions_decorator import requires_resource_permission
from app.errors.app_error import AppError
from app.settings.hybrid_flags import flags
from app.ai.knowledge.column_intel import profile_data_source
from app.ai.knowledge.schema_drift import compute_schema_drift

import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter(tags=["column-intel"])

# Per-table watermark lives under this key in DataSourceTable.metadata_json so a
# re-profile can skip tables whose row_count is unchanged since last profile.
_WATERMARK_KEY = "_profile_watermark"

# Profiler keys merged into columns[].metadata (description is NEVER touched).
_INTEL_KEYS = ("role", "values", "distinct", "null_pct", "min", "max")


class ProfileRequest(BaseModel):
    table_name: Optional[str] = None
    force: bool = False               # re-profile even tables whose row_count is unchanged


class PretrainRequest(BaseModel):
    table_name: Optional[str] = None
    suggest_knowledge: bool = True   # also AI-suggest table/metric knowledge (pending)
    auto_approve: bool = False        # flip the freshly-proposed pending rows to approved
    force: bool = False               # re-profile even tables whose row_count is unchanged


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower().strip() if ch.isalnum())


async def _load_ds(db, data_source_id, organization):
    res = await db.execute(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization.id,
        )
    )
    ds = res.scalar_one_or_none()
    if ds is None:
        raise AppError.not_found("data_source.not_found", "Data source not found")
    return ds


async def _load_active_tables(db, data_source_id):
    res = await db.execute(
        select(DataSourceTable).where(
            DataSourceTable.datasource_id == str(data_source_id),
            DataSourceTable.is_active == True,  # noqa: E712
        )
    )
    return list(res.scalars().all())


@router.post("/data_sources/{data_source_id}/profile", response_model=dict)
@requires_resource_permission("data_source", "view_schema")
async def profile_columns(
    data_source_id: str,
    payload: ProfileRequest = Body(default=ProfileRequest()),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
):
    if not getattr(flags, "COLUMN_INTEL", False):
        return {"disabled": True, "data_source_id": data_source_id}

    ds = await _load_ds(db, data_source_id, organization)

    # Profile EVERY active table (connector = many tables), scoped per table.
    written, unmatched, reports, total_rows, n_tables = await _profile_all_tables(
        db, ds, data_source_id, explicit_table=payload.table_name, force=payload.force
    )
    if not reports:
        return {"ok": False, "error": "no tables could be profiled", "data_source_id": str(ds.id)}
    await db.commit()

    first = reports[0]
    return {
        "ok": True,
        "data_source_id": str(ds.id),
        "table": first.get("table"),
        "tables_profiled": n_tables,
        "skipped_unchanged": first.get("_skipped_unchanged", 0),
        "row_count": total_rows,
        "columns_profiled": sum(len(r.get("columns", [])) for r in reports),
        "columns_written": written,
        "columns_unmatched": unmatched,
        "profile": first.get("columns", []),
    }


@router.get("/data_sources/{data_source_id}/schema-drift", response_model=dict)
@requires_resource_permission("data_source", "view_schema")
async def schema_drift(
    data_source_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Read-only diff of the LIVE engine schema vs the STORED active-table schema.

    Reports tables/columns added live-but-not-stored ("added") and stored-but-gone-
    from-live ("removed"). No persistence. Gated ``flags.COLUMN_INTEL`` (returns
    {disabled:True} when off). Never 500s — fail-soft to {ok:False,error}.
    """
    if not getattr(flags, "COLUMN_INTEL", False):
        return {"disabled": True, "data_source_id": data_source_id}

    try:
        ds = await _load_ds(db, data_source_id, organization)
        stored_tables = await _load_active_tables(db, data_source_id)
        try:
            client = ds.get_client()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "data_source_id": str(ds.id),
                    "error": f"could not obtain data-source client: {e}"}
        result = compute_schema_drift(client, stored_tables, _norm)
        result["data_source_id"] = str(ds.id)
        return result
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001 — never 500
        return {"ok": False, "data_source_id": data_source_id,
                "error": f"schema-drift failed: {e}"}


async def _table_row_count(ds, table_name) -> Optional[int]:
    """Live COUNT(*) for a single table via the data-source client. None on failure.

    Mirrors the row_count query in ``column_intel.profile_data_source``.
    """
    if not table_name:
        return None
    try:
        from app.ai.knowledge.column_intel import _is_read_only_sql, _quote_ident
        client = ds.get_client()
        qt = _quote_ident(table_name)
        sql = f"SELECT COUNT(*) AS n FROM {qt}"
        if not _is_read_only_sql(sql):
            return None
        df = await client.aexecute_query(sql)
        if df is not None and len(df) > 0:
            return int(df.iloc[0, 0] or 0)
    except Exception:
        return None
    return None


async def _store_profile(db, data_source_id, report, only_table=None):
    """Merge a profile report into active tables' columns[].metadata.

    When ``only_table`` is given, the merge is scoped to that single table
    (by name) so multi-table connectors don't cross-contaminate columns that
    share a name across tables (e.g. ArtistId in Album and Artist).

    NEVER touches ``description`` or non-intel metadata keys. Returns
    ``(columns_written, columns_unmatched)``. Does NOT commit (caller commits).
    """
    by_name = {_norm(c["name"]): c for c in report.get("columns", [])}
    tables = await _load_active_tables(db, data_source_id)
    if only_table is not None:
        tables = [t for t in tables if _norm(t.name) == _norm(only_table)]
    columns_written = 0

    for t in tables:
        cols = t.columns
        if not isinstance(cols, list) or not cols:
            continue
        changed = False
        for entry in cols:
            if not isinstance(entry, dict):
                continue
            prof = by_name.get(_norm(entry.get("name") or ""))
            if not prof:
                continue
            meta = entry.get("metadata")
            if not isinstance(meta, dict):
                meta = {}
            for k in _INTEL_KEYS:
                v = prof.get(k)
                if k == "values" and not v:
                    continue
                meta[k] = v
            entry["metadata"] = meta
            columns_written += 1
            changed = True
        if changed:
            flag_modified(t, "columns")

    matched_norm = {_norm(e.get("name") or "")
                    for t in tables if isinstance(t.columns, list)
                    for e in t.columns if isinstance(e, dict)}
    unmatched = [p["name"] for p in report.get("columns", [])
                 if _norm(p["name"]) not in matched_norm]
    return columns_written, unmatched


def _read_watermark(table) -> Optional[int]:
    """Stored per-table row_count watermark, or None if absent/unreadable."""
    try:
        meta = getattr(table, "metadata_json", None)
        if isinstance(meta, dict):
            wm = meta.get(_WATERMARK_KEY)
            if isinstance(wm, dict):
                rc = wm.get("row_count")
                return int(rc) if rc is not None else None
    except Exception:
        return None
    return None


def _write_watermark(table, row_count) -> None:
    """Persist the new row_count watermark onto metadata_json (flag_modified;
    caller commits). No-op when row_count is None."""
    if row_count is None:
        return
    try:
        meta = getattr(table, "metadata_json", None)
        if not isinstance(meta, dict):
            meta = {}
        wm = meta.get(_WATERMARK_KEY)
        if not isinstance(wm, dict):
            wm = {}
        wm["row_count"] = int(row_count)
        meta[_WATERMARK_KEY] = wm
        table.metadata_json = meta
        flag_modified(table, "metadata_json")
    except Exception:
        pass


async def _profile_all_tables(db, ds, data_source_id, explicit_table=None, force=False, progress=None):
    """Profile EVERY active table of the data source (a connector has many).

    Returns ``(columns_written, unmatched, reports, total_rows, table_count)`` —
    the 5-tuple is UNCHANGED for backward-compatible positional unpacking. The
    incremental skip count is stashed on each emitted report dict
    (``report["_skipped_unchanged"]`` on the first report) instead of widening the
    tuple.

    CHANGED-TABLE SKIP (Task 2): before profiling a table, compute its current
    live row_count and compare to the stored watermark on the table row
    (``metadata_json[_WATERMARK_KEY]['row_count']``). If EQUAL and not ``force``,
    skip the re-profile and count it as "unchanged". The new row_count is written
    back as the watermark after a successful profile.

    Each table is profiled + stored scoped to itself. Fail-soft per table — one
    bad table never aborts the rest. Falls back to the engine default table when
    the DB has no active-table rows yet.
    """
    active_tables = await _load_active_tables(db, data_source_id)
    by_norm_name = {_norm(t.name): t for t in active_tables}

    if explicit_table:
        names = [explicit_table]
    else:
        names = [t.name for t in active_tables] or [None]

    total_written = 0
    unmatched: list = []
    reports: list = []
    total_rows = 0
    done = 0
    skipped_unchanged = 0
    n_total = len(names)
    ds_label = getattr(ds, "name", None) or str(data_source_id)[:8]

    def _report_progress(idx, table_name, written, skipped):
        """Emit a per-table log line + invoke the optional progress callback so
        the caller (train orchestrator) can surface live progress to the UI."""
        logger.info(
            "[profile] %s · table %d/%d %r · %s (%d cols written)",
            ds_label, idx, n_total, table_name,
            "skipped (unchanged)" if skipped else "profiled", written,
        )
        if progress is not None:
            try:
                progress(done=idx, total=n_total, table=table_name, written=written)
            except Exception:  # noqa: BLE001 — progress is best-effort, never fatal
                pass

    for i, nm in enumerate(names, start=1):
        t0 = time.monotonic()
        try:
            tbl_row = by_norm_name.get(_norm(nm)) if nm else None

            # ── incremental skip: unchanged row_count (and not forced) ────────
            if tbl_row is not None and not force:
                prev = _read_watermark(tbl_row)
                if prev is not None:
                    cur = await _table_row_count(ds, nm)
                    if cur is not None and cur == prev:
                        skipped_unchanged += 1
                        total_rows += cur
                        _report_progress(i, nm, 0, skipped=True)
                        continue

            logger.info("[profile] %s · table %d/%d %r · profiling…", ds_label, i, n_total, nm)
            rep = await profile_data_source(ds, table_name=nm)
            if not rep.get("ok"):
                logger.warning("[profile] %s · table %r returned not-ok", ds_label, nm)
                _report_progress(i, nm, 0, skipped=False)
                continue
            w, u = await _store_profile(db, data_source_id, rep, only_table=nm)
            total_written += w
            unmatched += u
            reports.append(rep)
            rc = int(rep.get("row_count") or 0)
            total_rows += rc

            # write the fresh watermark on a successful profile (caller commits)
            if tbl_row is not None:
                _write_watermark(tbl_row, rc)
            done += 1
            logger.info("[profile] %s · table %r done in %.1fs (%d cols)", ds_label, nm, time.monotonic() - t0, w)
            _report_progress(i, nm, w, skipped=False)
        except Exception as e:  # noqa: BLE001 — never let one table kill the batch
            logger.warning("[profile] %s · table %r failed after %.1fs: %s", ds_label, nm, time.monotonic() - t0, e)
            _report_progress(i, nm, 0, skipped=False)
            continue

    if reports:
        reports[0]["_skipped_unchanged"] = skipped_unchanged
    return total_written, unmatched, reports, total_rows, done


def _merge_dimensions(reports, *, cap: int = 12):
    out = []
    for rep in reports:
        for d in _dimensions_summary(rep, cap=cap):
            out.append(d)
            if len(out) >= cap:
                return out
    return out


def _dimensions_summary(report, *, cap: int = 12):
    """Compact dimension digest for the UI / robot stream — name + sample values."""
    out = []
    for c in report.get("columns", []):
        if c.get("role") != "dimension":
            continue
        vals = c.get("values") or []
        if not vals:
            continue
        out.append({
            "name": c.get("name"),
            "values": [str(v) for v in vals[:8]],
            "distinct": c.get("distinct"),
        })
        if len(out) >= cap:
            break
    return out


@router.post("/data_sources/{data_source_id}/pretrain", response_model=dict)
@requires_resource_permission("data_source", "view_schema")
async def pretrain_data_source(
    data_source_id: str,
    payload: PretrainRequest = Body(default=PretrainRequest()),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
):
    """One-click pre-train (Batch C / P6).

    1. Profile every column (role / real values / distinct / nulls) and store it
       into the schema metadata so the agent is expert BEFORE the first question.
    2. Optionally AI-suggest table/metric knowledge (lands ``pending`` for review).
    3. Optionally auto-approve those freshly-proposed rows (skip the review queue).

    Gated ``flags.COLUMN_INTEL`` (returns {disabled:True} when off). Never 500s on
    the knowledge step — column intel is the guaranteed win, suggestion is best-effort.
    """
    if not getattr(flags, "COLUMN_INTEL", False):
        return {"disabled": True, "data_source_id": data_source_id}

    ds = await _load_ds(db, data_source_id, organization)

    # Profile EVERY active table of the source (connector = many tables).
    written, unmatched, reports, total_rows, n_tables = await _profile_all_tables(
        db, ds, data_source_id, explicit_table=payload.table_name, force=payload.force
    )
    if not reports:
        return {"ok": False, "error": "no tables could be profiled", "data_source_id": str(ds.id)}
    await db.commit()
    report = reports[0]

    knowledge = {"proposed": 0, "approved": 0, "enabled": False}
    if payload.suggest_knowledge and (flags.SEMANTIC_LAYER or flags.METRICS_CATALOG):
        knowledge["enabled"] = True
        try:
            from app.services.llm_service import LLMService
            from app.ai.brain.knowledge_proposer import propose_knowledge_from_schema

            model = await LLMService().get_default_model(db, organization, current_user, is_small=True)
            result = await propose_knowledge_from_schema(
                db, organization=organization, data_source=ds, model=model, focus="both",
            )
            sem_ids = list(result.get("semantics", []) or [])
            met_ids = list(result.get("metrics", []) or [])
            knowledge["proposed"] = len(sem_ids) + len(met_ids)

            if payload.auto_approve and (sem_ids or met_ids):
                approved = await _auto_approve(db, sem_ids, met_ids)
                knowledge["approved"] = approved
                await db.commit()
        except Exception as e:  # best-effort — column intel already committed
            knowledge["error"] = str(e)[:200]

    return {
        "ok": True,
        "data_source_id": str(ds.id),
        "table": report.get("table"),
        "tables_profiled": n_tables,
        "skipped_unchanged": report.get("_skipped_unchanged", 0),
        "row_count": total_rows,
        "columns_profiled": sum(len(r.get("columns", [])) for r in reports),
        "columns_written": written,
        "columns_unmatched": unmatched,
        "dimensions": _merge_dimensions(reports),
        "knowledge": knowledge,
    }


async def _auto_approve(db, sem_ids, met_ids) -> int:
    """Flip freshly-proposed pending rows to approved. Freshly proposed rows have
    NO competing approved-current row (the proposer never overwrites approved), so a
    plain status flip can't collide with the bitemporal partial-unique index."""
    from sqlalchemy import update as _sa_update
    n = 0
    try:
        from app.models.semantic_table import SemanticTable
        if sem_ids:
            await db.execute(
                _sa_update(SemanticTable)
                .where(SemanticTable.id.in_([str(i) for i in sem_ids]))
                .values(status="approved")
            )
            n += len(sem_ids)
    except Exception:
        pass
    try:
        from app.models.metric_definition import MetricDefinition
        if met_ids:
            await db.execute(
                _sa_update(MetricDefinition)
                .where(MetricDefinition.id.in_([str(i) for i in met_ids]))
                .values(status="approved")
            )
            n += len(met_ids)
    except Exception:
        pass
    return n


@router.get("/data_sources/{data_source_id}/columns/intel", response_model=dict)
@requires_resource_permission("data_source", "view_schema")
async def get_column_intel(
    data_source_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
):
    if not getattr(flags, "COLUMN_INTEL", False):
        return {"disabled": True, "data_source_id": data_source_id}

    ds = await _load_ds(db, data_source_id, organization)
    tables = await _load_active_tables(db, data_source_id)

    out_tables = []
    for t in tables:
        cols = t.columns if isinstance(t.columns, list) else []
        items = []
        for entry in cols:
            if not isinstance(entry, dict):
                continue
            meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            items.append({
                "name": entry.get("name"),
                "dtype": entry.get("dtype"),
                "description": entry.get("description"),
                "role": meta.get("role"),
                "values": meta.get("values") or [],
                "distinct": meta.get("distinct"),
                "null_pct": meta.get("null_pct"),
                "min": meta.get("min"),
                "max": meta.get("max"),
            })
        out_tables.append({
            "table_id": str(t.id),
            "table_name": t.name,
            "columns": items,
        })

    return {"ok": True, "data_source_id": str(ds.id), "tables": out_tables}
