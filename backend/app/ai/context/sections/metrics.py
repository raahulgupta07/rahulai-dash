"""MetricsCatalogSection — Knowledge Layer Phase 4 (read).

Surfaces approved named business metrics (name -> definition, table_ref,
sql_calc) so the planner reuses the canonical definition instead of inventing
one. Same shape as brain/skills sections; ``render()`` is self-contained and
returns an empty string when there are no items.

P7 VERIFIED_METRICS extension: MetricItem carries an ``is_locked`` flag and
an optional ``last_value`` float. When is_locked=True the section renders an
[AUTHORITATIVE] marker so the planner knows the metric value is pre-verified
and should be used as-is rather than recomputed from scratch.
"""
from __future__ import annotations
from typing import ClassVar, List, Optional
from pydantic import BaseModel
from app.ai.context.sections.base import ContextSection


class MetricItem(BaseModel):
    name: str
    definition: str = ""
    table_ref: str = ""
    sql_calc: str = ""
    owner: Optional[str] = None
    # VERIFIED_METRICS (P7): populated by MetricsContextBuilder when flag is ON.
    is_locked: bool = False
    last_value: Optional[float] = None


class MetricsCatalogSection(ContextSection):
    tag_name: ClassVar[str] = "metrics_catalog"
    items: List[MetricItem] = []

    def render(self) -> str:
        if not self.items:
            return ""
        lines: List[str] = [
            "<metrics_catalog>",
            "Approved business metrics. Prefer these definitions; use "
            "resolve_metric to fetch a metric's full SQL.",
        ]
        for m in self.items:
            parts = [f"- {m.name}"]
            # VERIFIED_METRICS: locked metrics get an authoritative marker so
            # the planner knows the value is pre-verified and executable.
            if m.is_locked:
                if m.last_value is not None:
                    parts.append(f" [AUTHORITATIVE, last_value={m.last_value:.4g}]")
                else:
                    parts.append(" [AUTHORITATIVE]")
            if m.definition and m.definition.strip():
                parts.append(f": {m.definition.strip()}")
            if m.table_ref and m.table_ref.strip():
                parts.append(f" ({m.table_ref.strip()})")
            if m.sql_calc and m.sql_calc.strip():
                calc = " ".join(m.sql_calc.split())
                if len(calc) > 200:
                    calc = calc[:200] + "…"
                parts.append(f" [{calc}]")
            lines.append("".join(parts))
        lines.append("</metrics_catalog>")
        return "\n".join(lines)
