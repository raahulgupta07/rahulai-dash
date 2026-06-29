"""ProfileV2Section — Deep Profiler v2 context section (Wave1 P1).

Surfaces the per-column role catalog (DIMENSION / STATE / MEASURE /
IDENTIFIER / TEMPORAL) + top-3 values + variant warnings produced by
``app.ai.knowledge.profile_v2.profile_table_v2``.

Same shape as every other section: Pydantic ContextSection + self-contained
``render()`` that returns "" when empty (flag OFF or no data).
"""
from __future__ import annotations

from typing import ClassVar, Dict, List, Optional
from pydantic import BaseModel

from app.ai.context.sections.base import ContextSection


# ---------------------------------------------------------------------------
# Item models
# ---------------------------------------------------------------------------

class ProfileV2TopValue(BaseModel):
    value: Optional[str] = None
    count: Optional[int] = None


class ProfileV2ColumnItem(BaseModel):
    name: str
    role: str                              # DIMENSION | STATE | MEASURE | IDENTIFIER | TEMPORAL
    top_values: List[ProfileV2TopValue] = []
    variants_warning: Optional[str] = None
    normalize_instruction: Optional[str] = None   # VALUE_NORMALIZE canonical guardrail


class ProfileV2TableItem(BaseModel):
    table_name: str
    columns: List[ProfileV2ColumnItem] = []


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class ProfileV2Section(ContextSection):
    """Aggregated deep-profile blocks for all in-scope tables.

    Populated by ProfileV2ContextBuilder from DataSourceTable.metadata_json
    ['profile_v2'].  Renders empty string when no items (flag OFF = no DB hit
    = empty section).
    """
    tag_name: ClassVar[str] = "profile_v2"
    items: List[ProfileV2TableItem] = []

    def render(self) -> str:
        if not self.items:
            return ""

        # Bucket labels
        _ROLE_ORDER = ("DIMENSION", "STATE", "MEASURE", "IDENTIFIER", "TEMPORAL")
        _ROLE_LABEL: Dict[str, str] = {
            "DIMENSION":  "DIMENSIONS",
            "STATE":      "STATES",
            "MEASURE":    "MEASURES",
            "IDENTIFIER": "IDENTIFIERS",
            "TEMPORAL":   "TEMPORAL",
        }

        lines: List[str] = ["<profile_v2>"]

        for tbl in self.items:
            lines.append(f"  table: {tbl.table_name}")

            # Group by role
            buckets: Dict[str, List[ProfileV2ColumnItem]] = {r: [] for r in _ROLE_ORDER}
            for col in tbl.columns:
                role = col.role if col.role in buckets else "DIMENSION"
                buckets[role].append(col)

            for role in _ROLE_ORDER:
                cols = buckets[role]
                if not cols:
                    continue
                lines.append(f"    [{_ROLE_LABEL[role]}]")
                for c in cols:
                    tv_parts: List[str] = []
                    for tv in c.top_values[:3]:
                        if tv.value is not None:
                            s = str(tv.value)
                            if tv.count is not None:
                                s += f"({tv.count})"
                            tv_parts.append(s)

                    line = f"      {c.name}"
                    if tv_parts:
                        line += " — top: " + ", ".join(tv_parts)
                    if c.variants_warning:
                        short = (c.variants_warning[:60] + "…"
                                 if len(c.variants_warning) > 60
                                 else c.variants_warning)
                        line += f"  ⚠ {short}"

                    # Cap at ~120 chars
                    if len(line) > 120:
                        line = line[:119] + "…"
                    lines.append(line)

                    # VALUE_NORMALIZE: full canonical guardrail on its own line
                    # (untruncated so the map survives for the SQL planner).
                    if c.normalize_instruction:
                        instr = c.normalize_instruction
                        if len(instr) > 240:
                            instr = instr[:239] + "…"
                        lines.append(f"        ↳ {instr}")

        lines.append("</profile_v2>")
        return "\n".join(lines)
