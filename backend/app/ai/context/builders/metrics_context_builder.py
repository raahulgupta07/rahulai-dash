"""MetricsContextBuilder — Knowledge Layer Phase 4 (read).

Injects APPROVED named metric definitions for the data sources in scope.
Self-gates on flags.METRICS_CATALOG (empty section when OFF, no scope, or on
any error). Mirrors the BrainContextBuilder/SkillContextBuilder shape exactly.
"""
from __future__ import annotations
import os
from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.hybrid_flags import flags
from app.models.metric_definition import MetricDefinition
from app.ai.context.sections.metrics import MetricsCatalogSection, MetricItem


def _top_k() -> int:
    """Top-K cap for query-relevant metric injection (env-overridable). Bounds
    the prompt as the metrics catalog grows (cf. arXiv:2605.22502). Only trims
    when there are MORE than K metrics."""
    try:
        k = int(os.getenv("HYBRID_METRICS_TOP_K", "12"))
        return k if k > 0 else 12
    except Exception:
        return 12


def _rank_metrics(query: str, rows: List[Any], k: int) -> List[Any]:
    """Rank metrics by token-Jaccard of (name + definition + table_ref) vs the
    normalized query; top-K. Any failure -> original order capped at K."""
    try:
        from app.ai.brain.query_cache_store import normalize_question, _tokens, _jaccard
        q_tokens = _tokens(normalize_question(query))
        if not q_tokens:
            return rows[:k]
        scored = []
        for r in rows:
            text = " ".join([r.name or "", r.definition or "", r.table_ref or ""])
            scored.append((_jaccard(q_tokens, _tokens(normalize_question(text))), r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:k]]
    except Exception:
        return rows[:k]


class MetricsContextBuilder:
    def __init__(self, db: AsyncSession, organization, data_source_ids: Optional[List[str]] = None):
        self.db = db
        self.organization = organization
        self.data_source_ids = data_source_ids

    async def build(self, query: Optional[str] = None) -> MetricsCatalogSection:
        if not flags.METRICS_CATALOG:
            return MetricsCatalogSection(items=[])
        if not self.data_source_ids:
            return MetricsCatalogSection(items=[])
        try:
            stmt = (
                select(MetricDefinition)
                .where(MetricDefinition.organization_id == str(self.organization.id))
                .where(MetricDefinition.data_source_id.in_([str(d) for d in self.data_source_ids]))
                .where(MetricDefinition.status == "approved")
                .order_by(MetricDefinition.name.asc())
            )
            # Bi-temporal (HYBRID_BITEMPORAL): only currently-valid versions reach
            # the agent. No-op (None) when the flag is OFF.
            from app.ai.brain import bitemporal
            cond = bitemporal.current_condition(MetricDefinition)
            if cond is not None:
                stmt = stmt.where(cond)
            rows = list((await self.db.execute(stmt)).scalars().all())
            k = _top_k()
            if query and query.strip() and len(rows) > k:
                rows = _rank_metrics(query, rows, k)
            verified_on = flags.VERIFIED_METRICS
            items = []
            for r in rows:
                is_locked = bool(getattr(r, "is_locked", False)) if verified_on else False
                last_val: Optional[float] = None
                if verified_on and is_locked:
                    try:
                        raw = getattr(r, "last_value", None)
                        if raw is not None:
                            last_val = float(raw)
                    except Exception:
                        last_val = None
                items.append(
                    MetricItem(
                        name=r.name,
                        definition=r.definition or "",
                        table_ref=r.table_ref or "",
                        sql_calc=r.sql_calc or "",
                        owner=r.owner,
                        is_locked=is_locked,
                        last_value=last_val,
                    )
                )
            return MetricsCatalogSection(items=items)
        except Exception:
            return MetricsCatalogSection(items=[])
