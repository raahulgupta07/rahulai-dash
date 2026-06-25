"""PipelineLogicSection — Code Enrich context section (Wave1 P6).

Surfaces the per-table pipeline logic (grain + derived-column formulas +
population filter) extracted from source DDL / view definitions by
``app.ai.knowledge.code_enrich``.

Same shape as every other section: Pydantic ContextSection + self-contained
``render()`` that returns "" when empty (flag OFF or no data).

Render output (injected as a prompt block):

    ## PIPELINE LOGIC (from source code)
    ### <table_name>
    grain: <one-sentence grain>
    population: <one-sentence population>
    formulas:
      <col>: <expr>
      ...

Gate: flags.CODE_ENRICH.  Empty section = zero DB hit when off.
"""
from __future__ import annotations

from typing import ClassVar, Dict, List, Optional
from pydantic import BaseModel

from app.ai.context.sections.base import ContextSection


# ---------------------------------------------------------------------------
# Item models
# ---------------------------------------------------------------------------

class FormulaItem(BaseModel):
    col: str
    expr: str


class PipelineLogicTableItem(BaseModel):
    table_name: str
    grain: str = ""
    formulas: List[FormulaItem] = []
    population: str = ""


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class PipelineLogicSection(ContextSection):
    """Aggregated pipeline-logic blocks for all in-scope tables.

    Populated by PipelineLogicContextBuilder from
    DataSourceTable.metadata_json['pipeline_logic'].
    Renders "" when no items (flag OFF = no DB hit = empty section).
    """
    tag_name: ClassVar[str] = "pipeline_logic"
    items: List[PipelineLogicTableItem] = []

    def render(self) -> str:
        if not self.items:
            return ""

        lines: List[str] = ["## PIPELINE LOGIC (from source code)"]

        for tbl in self.items:
            lines.append(f"### {tbl.table_name}")
            if tbl.grain:
                lines.append(f"grain: {tbl.grain}")
            if tbl.population and tbl.population.lower() != "all rows included":
                lines.append(f"population: {tbl.population}")
            if tbl.formulas:
                lines.append("formulas:")
                for f in tbl.formulas[:20]:  # cap at 20 formulas per table
                    expr_short = f.expr[:120] + "…" if len(f.expr) > 120 else f.expr
                    lines.append(f"  {f.col}: {expr_short}")
            lines.append("")  # blank line between tables

        # Strip trailing blank line
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)
