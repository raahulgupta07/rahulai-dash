"""PipelineLogicContextBuilder — Code Enrich context builder (Wave1 P6).

Reads DataSourceTable.metadata_json['pipeline_logic'] blobs for ACTIVE tables
in scope and assembles a PipelineLogicSection for the planner prompt.

Gate: flags.CODE_ENRICH.  When OFF returns an empty PipelineLogicSection with
zero DB hits.  Mirrors ProfileV2ContextBuilder shape exactly.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.hybrid_flags import flags
from app.ai.context.sections.pipeline_logic import (
    PipelineLogicSection,
    PipelineLogicTableItem,
    FormulaItem,
)

logger = logging.getLogger(__name__)

_EMPTY = PipelineLogicSection(items=[])


class PipelineLogicContextBuilder:
    """Build a PipelineLogicSection from stored metadata_json['pipeline_logic'] blobs.

    Parameters
    ----------
    db : AsyncSession
    organization :
        ORM Organization row (needs .id).
    data_source_ids : list[str] or None
        Scope to these data sources.  None / empty → empty section.
    """

    def __init__(
        self,
        db: AsyncSession,
        organization,
        data_source_ids: Optional[List[str]] = None,
    ) -> None:
        self.db = db
        self.organization = organization
        self.data_source_ids = data_source_ids

    async def build(self, query: Optional[str] = None) -> PipelineLogicSection:
        # Flag OFF → instant empty section, zero DB reads.
        if not flags.CODE_ENRICH:
            return _EMPTY
        if not self.data_source_ids:
            return _EMPTY

        try:
            return await self._build()
        except Exception as e:
            logger.warning("PipelineLogicContextBuilder.build failed: %s", e)
            return _EMPTY

    async def _build(self) -> PipelineLogicSection:
        from app.models.datasource_table import DataSourceTable
        from app.models.data_source import DataSource

        # Only active tables belonging to in-scope, approved sources.
        stmt = (
            select(DataSourceTable)
            .join(DataSource, DataSource.id == DataSourceTable.datasource_id)
            .where(DataSource.organization_id == str(self.organization.id))
            .where(DataSource.id.in_([str(d) for d in self.data_source_ids]))
            .where(DataSourceTable.is_active.is_(True))
            .order_by(DataSourceTable.name.asc())
        )
        rows = list((await self.db.execute(stmt)).scalars().all())

        items: List[PipelineLogicTableItem] = []
        for tbl in rows:
            meta = tbl.metadata_json
            if not isinstance(meta, dict):
                continue
            pl = meta.get("pipeline_logic")
            if not isinstance(pl, dict) or not pl:
                continue

            grain = str(pl.get("grain") or "").strip()
            population = str(pl.get("population") or "").strip()
            raw_formulas = pl.get("formulas") or []

            formula_items: List[FormulaItem] = []
            for f in raw_formulas:
                if not isinstance(f, dict):
                    continue
                col = str(f.get("col") or "").strip()
                expr = str(f.get("expr") or "").strip()
                if col and expr:
                    formula_items.append(FormulaItem(col=col, expr=expr))

            # Only include tables that have at least a grain or a formula.
            if grain or formula_items:
                items.append(
                    PipelineLogicTableItem(
                        table_name=tbl.name,
                        grain=grain,
                        formulas=formula_items,
                        population=population,
                    )
                )

        return PipelineLogicSection(items=items)
