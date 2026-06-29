"""ProfileV2ContextBuilder — Deep Profiler v2 (Wave1 P1).

Injects the per-column role catalog (DIMENSION / STATE / MEASURE /
IDENTIFIER / TEMPORAL) + top-3 values + variant warnings for APPROVED,
ACTIVE DataSourceTables whose metadata_json['profile_v2'] has been
populated by ``profile_table_v2``.

Gate: flags.PROFILE_V2.  When OFF returns an empty ProfileV2Section with
zero DB hits.  Mirrors SemanticContextBuilder / MetricsContextBuilder shape
exactly.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.hybrid_flags import flags
from app.ai.context.sections.profile_v2 import (
    ProfileV2Section,
    ProfileV2TableItem,
    ProfileV2ColumnItem,
    ProfileV2TopValue,
)

logger = logging.getLogger(__name__)

_EMPTY = ProfileV2Section(items=[])


class ProfileV2ContextBuilder:
    """Build a ProfileV2Section from stored metadata_json['profile_v2'] blobs.

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

    async def build(self, query: Optional[str] = None) -> ProfileV2Section:
        # Flag OFF → instant empty section, zero DB reads.
        if not flags.PROFILE_V2:
            return _EMPTY
        if not self.data_source_ids:
            return _EMPTY

        try:
            return await self._build()
        except Exception as e:
            logger.warning("ProfileV2ContextBuilder.build failed: %s", e)
            return _EMPTY

    async def _build(self) -> ProfileV2Section:
        from app.models.datasource_table import DataSourceTable
        from app.models.data_source import DataSource

        # Only tables that are active AND belong to an approved in-scope source.
        stmt = (
            select(DataSourceTable)
            .join(DataSource, DataSource.id == DataSourceTable.datasource_id)
            .where(DataSource.organization_id == str(self.organization.id))
            .where(DataSource.id.in_([str(d) for d in self.data_source_ids]))
            .where(DataSourceTable.is_active.is_(True))
            .order_by(DataSourceTable.name.asc())
        )
        rows = list((await self.db.execute(stmt)).scalars().all())

        items: List[ProfileV2TableItem] = []
        for tbl in rows:
            meta = tbl.metadata_json
            if not isinstance(meta, dict):
                continue
            profile = meta.get("profile_v2")
            if not isinstance(profile, dict) or not profile:
                continue

            col_items: List[ProfileV2ColumnItem] = []
            for col_name, info in profile.items():
                if not isinstance(info, dict):
                    continue
                role = info.get("role", "DIMENSION")
                raw_tv = info.get("top_values") or []
                tv_items = [
                    ProfileV2TopValue(
                        value=(str(tv.get("value")) if tv.get("value") is not None else None),
                        count=(int(tv["count"]) if tv.get("count") is not None else None),
                    )
                    for tv in raw_tv[:3]
                    if isinstance(tv, dict)
                ]
                col_items.append(
                    ProfileV2ColumnItem(
                        name=col_name,
                        role=role,
                        top_values=tv_items,
                        variants_warning=info.get("variants_warning") or None,
                        normalize_instruction=info.get("normalize_instruction") or None,
                    )
                )

            if col_items:
                items.append(ProfileV2TableItem(
                    table_name=tbl.name,
                    columns=col_items,
                ))

        return ProfileV2Section(items=items)
