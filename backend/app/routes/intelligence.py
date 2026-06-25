"""Intelligence layer data API (read-only).

Feeds the Studio → Intelligence rail (the 8 hybrid capability layers from
Wave 1+2). One endpoint, switch on `layer`. Org-scoped, fail-soft: any error
degrades to an empty table + note, never 500s the rail. Additive — no core
files touched beyond router registration. Toggles are NOT here: the rail
reuses the existing GET/PUT /api/organization/hybrid-flags endpoints.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_db, get_current_organization
from app.core.auth import current_user
from app.models.user import User
from app.models.organization import Organization
from app.models.studio import StudioDataSource
from app.models.datasource_table import DataSourceTable
from app.models.metric_definition import MetricDefinition
from app.models.query_library import QueryLibraryItem
from app.settings.hybrid_flags import flags as _flags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

# layer -> (HYBRID_* env name, flags property name)
_LAYER_FLAG = {
    "profiler":   ("HYBRID_PROFILE_V2", "PROFILE_V2"),
    "codeenrich": ("HYBRID_CODE_ENRICH", "CODE_ENRICH"),
    "metrics":    ("HYBRID_VERIFIED_METRICS", "VERIFIED_METRICS"),
    "lazy":       ("HYBRID_PROFILE_V2", "PROFILE_V2"),
    "insights":   ("HYBRID_PROACTIVE_INSIGHTS", "PROACTIVE_INSIGHTS"),
    "forecast":   ("HYBRID_FORECAST", "FORECAST"),
    "golden":     ("HYBRID_GOLDEN_QUERIES", "GOLDEN_QUERIES"),
    "search":     ("HYBRID_SEMANTIC_SEARCH", "SEMANTIC_SEARCH"),
}


async def _studio_ds_ids(db: AsyncSession, studio_id: str) -> list[str]:
    if not studio_id:
        return []
    try:
        res = await db.execute(
            select(StudioDataSource.agent_id).where(StudioDataSource.studio_id == studio_id)
        )
        return [r[0] for r in res.all() if r[0]]
    except Exception as e:  # noqa
        logger.warning("intelligence: studio sources lookup failed: %s", e)
        return []


async def _active_tables(db: AsyncSession, ds_ids: list[str]) -> list[DataSourceTable]:
    if not ds_ids:
        return []
    try:
        res = await db.execute(
            select(DataSourceTable).where(
                DataSourceTable.datasource_id.in_(ds_ids),
                DataSourceTable.is_active.is_(True),
            )
        )
        return list(res.scalars().all())
    except Exception as e:  # noqa
        logger.warning("intelligence: active tables lookup failed: %s", e)
        return []


def _empty(layer: str, env: str, enabled: bool, note: str) -> dict:
    return {"layer": layer, "flag": env, "enabled": enabled,
            "stats": None, "table": None, "note": note}


@router.get("/layer/{layer}")
async def get_layer(
    layer: str,
    studio_id: str = Query("", description="Studio id to scope data sources"),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Return real data for one intelligence layer (read-only, fail-soft)."""
    if layer not in _LAYER_FLAG:
        return _empty(layer, "", False, "Unknown layer.")
    env, prop = _LAYER_FLAG[layer]
    enabled = bool(getattr(_flags, prop, False))
    org_id = organization.id

    try:
        ds_ids = await _studio_ds_ids(db, studio_id)

        # ---- PROFILER: profile_v2 catalog across the studio's tables ----
        if layer == "profiler":
            tables = await _active_tables(db, ds_ids)
            rows, n_cols, n_classified, n_variants = [], 0, 0, 0
            for tb in tables:
                meta = tb.metadata_json or {}
                prof = meta.get("profile_v2") if isinstance(meta, dict) else None
                if not isinstance(prof, dict):
                    continue
                for col, info in prof.items():
                    if not isinstance(info, dict):
                        continue
                    n_cols += 1
                    role = info.get("role", "")
                    if role:
                        n_classified += 1
                    tv = info.get("top_values") or []
                    top = " · ".join(
                        f"{t.get('value')} ({t.get('count')})" for t in tv[:3]
                        if isinstance(t, dict)
                    )
                    warn = info.get("variants_warning")
                    if warn:
                        n_variants += 1
                        top = (top + f"  ⚠ {warn}") if top else f"⚠ {warn}"
                    rows.append([f"{tb.name}.{col}", role or "—", top or "—"])
            if not rows:
                return _empty(layer, env, enabled,
                              "No profile_v2 yet. Enable Deep Profiler and run a train (or query) to populate.")
            pct = int(round(100 * n_classified / n_cols)) if n_cols else 0
            return {
                "layer": layer, "flag": env, "enabled": enabled,
                "stats": [
                    {"n": str(len(tables)), "l": "Tables"},
                    {"n": str(n_cols), "l": "Columns"},
                    {"n": f"{pct}%", "l": "Classified"},
                    {"n": str(n_variants), "l": "Variants"},
                ],
                "table": {"title": "Column catalog", "head": ["Column", "Role", "Top values"], "rows": rows},
                "note": None,
            }

        # ---- CODE ENRICH: pipeline_logic per table ----
        if layer == "codeenrich":
            tables = await _active_tables(db, ds_ids)
            rows = []
            for tb in tables:
                meta = tb.metadata_json or {}
                pl = meta.get("pipeline_logic") if isinstance(meta, dict) else None
                if not isinstance(pl, dict):
                    continue
                grain = pl.get("grain") or "—"
                src = pl.get("source") or pl.get("source_method") or "—"
                rows.append([tb.name, str(grain), str(src)])
            if not rows:
                return _empty(layer, env, enabled,
                              "No pipeline_logic yet. Enable Code Enrich and run a train to extract grain/formulas from source.")
            return {"layer": layer, "flag": env, "enabled": enabled, "stats": None,
                    "table": {"title": "Extracted pipeline logic", "head": ["Table", "Grain", "Source"], "rows": rows},
                    "note": None}

        # ---- VERIFIED METRICS ----
        if layer == "metrics":
            res = await db.execute(
                select(MetricDefinition).where(MetricDefinition.organization_id == org_id)
            )
            mets = list(res.scalars().all())
            rows = []
            for m in mets:
                locked = "LOCKED" if getattr(m, "is_locked", False) else "—"
                lv = getattr(m, "last_value", None)
                rows.append([m.name, locked, ("—" if lv is None else str(lv)), getattr(m, "status", "")])
            if not rows:
                return _empty(layer, env, enabled,
                              "No metrics defined. Add metrics in Knowledge → Metrics; lock one to make it authoritative.")
            n_locked = sum(1 for m in mets if getattr(m, "is_locked", False))
            return {"layer": layer, "flag": env, "enabled": enabled,
                    "stats": [{"n": str(len(mets)), "l": "Metrics"}, {"n": str(n_locked), "l": "Locked"}],
                    "table": {"title": "Metric library", "head": ["Metric", "Lock", "Last value", "Status"], "rows": rows},
                    "note": None}

        # ---- GOLDEN QUERIES ----
        if layer == "golden":
            res = await db.execute(
                select(QueryLibraryItem).where(QueryLibraryItem.organization_id == org_id)
            )
            qs = list(res.scalars().all())
            rows = []
            for q in qs:
                gold = "★ GOLDEN" if getattr(q, "is_golden", False) else (getattr(q, "status", "") or "—")
                rows.append([q.name, gold, str(getattr(q, "verified_count", 0)), str(getattr(q, "run_count", 0))])
            if not rows:
                return _empty(layer, env, enabled,
                              "No saved queries yet. Queries are captured from successful chats; thumbs-up or repeats promote them to golden.")
            n_gold = sum(1 for q in qs if getattr(q, "is_golden", False))
            return {"layer": layer, "flag": env, "enabled": enabled,
                    "stats": [{"n": str(len(qs)), "l": "Queries"}, {"n": str(n_gold), "l": "Golden"}],
                    "table": {"title": "Query library", "head": ["Question", "Status", "Verified", "Used"], "rows": rows},
                    "note": None}

        # ---- HYBRID SEARCH + KG (scaffold) ----
        if layer == "search":
            edges = []
            try:
                from app.models.brain_graph_edge import BrainGraphEdge  # local import, optional
                res = await db.execute(
                    select(BrainGraphEdge).where(BrainGraphEdge.organization_id == org_id).limit(50)
                )
                for e in res.scalars().all():
                    edges.append([
                        str(getattr(e, "src_entity", "?")),
                        str(getattr(e, "relation", "related_to")),
                        str(getattr(e, "dst_entity", "?")),
                    ])
            except Exception as e:  # noqa
                logger.debug("intelligence: KG edges read failed: %s", e)
            note = "Scaffold — enable Hybrid Search to populate the index; prompt injection ships in a later wave."
            if not edges:
                return _empty(layer, env, enabled, note)
            return {"layer": layer, "flag": env, "enabled": enabled, "stats": None,
                    "table": {"title": "Knowledge graph edges", "head": ["From", "Relation", "To"], "rows": edges},
                    "note": note}

        # ---- transient layers: no persisted store ----
        if layer == "lazy":
            return _empty(layer, env, enabled,
                          "Lazy profiling runs at query time (cache-miss → inline profile). Activity isn't persisted; it shares the Deep Profiler flag + the LAZY_PROFILE_V2_DISABLED kill-switch.")
        if layer == "insights":
            return _empty(layer, env, enabled,
                          "Insights are computed per result and rendered as chips under the answer (z-score + IQR + spike). They are not stored on the agent.")
        if layer == "forecast":
            return _empty(layer, env, enabled,
                          "Forecasting adds the forecast_df tool the agent calls on demand. Requires an image rebuild (prophet) before it runs live.")

        return _empty(layer, env, enabled, "No data.")
    except Exception as e:  # noqa
        logger.warning("intelligence.get_layer(%s) failed: %s", layer, e)
        return _empty(layer, env, enabled, "Data temporarily unavailable.")
