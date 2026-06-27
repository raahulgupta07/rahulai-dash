"""Phase-1 Semantic Layer API.

Stores and serves per-table and per-column *meaning* for a data source. This is
additive on top of dash's schema store (DataSourceTable -> ConnectionTable, which
remain the source of truth for actual table/column names + types). The GET endpoint
SEEDS empty SemanticTable/SemanticColumn rows from that schema store on demand so the
UI always has something to edit.

`described_pct` = ratio (0..1) of seeded tables whose `description` is non-empty
(tables-described ratio).
"""
import logging

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_async_db, get_current_organization
from app.errors import AppError, ErrorCode
from app.core.auth import current_user
from app.models.user import User
from app.models.organization import Organization
from app.models.data_source import DataSource
from app.models.datasource_table import DataSourceTable
from app.models.semantic_table import SemanticTable, SemanticColumn
from app.models.metric_definition import MetricDefinition
from app.models.query_library import QueryLibraryItem
from app.models.table_edge import TableEdge
from app.models.knowledge_doc import KnowledgeDoc
from app.ai.knowledge.docs_index import ingest_doc, search_docs
from app.schemas.semantic_schema import (
    SemanticTableRead,
    SemanticColumnRead,
    SemanticLayerResponse,
    SemanticLayerStats,
    SemanticTablePatch,
    SemanticColumnPatch,
)
from app.schemas.metric_schema import (
    MetricRead,
    MetricsResponse,
    MetricCreate,
    MetricPatch,
    MetricTestResult,
)
from app.schemas.query_library_schema import (
    QueryItemRead,
    QueryLibraryResponse,
    QueryCreate,
    QueryPatch,
    QueryRunResult,
)
from app.models.instruction import Instruction
from app.schemas.knowledge_assets_schema import AssetItemRead, AssetsResponse
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _enumerate_schema(data_source: DataSource) -> list[tuple[str, list[dict]]]:
    """Return [(table_name, [{name, type}, ...]), ...] from dash's schema store.

    Reads DataSourceTable rows; prefers the linked ConnectionTable schema (new
    architecture) and falls back to legacy columns stored directly on the
    DataSourceTable. Column dtype is best-effort.
    """
    result: list[tuple[str, list[dict]]] = []
    for dst in (data_source.tables or []):
        cols_src = None
        if getattr(dst, "connection_table", None) is not None and dst.connection_table.columns:
            cols_src = dst.connection_table.columns
        elif dst.columns:
            cols_src = dst.columns

        columns: list[dict] = []
        for col in (cols_src or []):
            if isinstance(col, dict):
                name = col.get("name")
                dtype = col.get("dtype") or col.get("type") or ""
            else:
                name = str(col)
                dtype = ""
            if name:
                columns.append({"name": name, "type": dtype or ""})
        result.append((dst.name, columns))
    return result


async def _load_semantic_tables(db: AsyncSession, org_id: str, data_source_id: str) -> list[SemanticTable]:
    res = await db.execute(
        select(SemanticTable)
        .where(
            SemanticTable.organization_id == org_id,
            SemanticTable.data_source_id == data_source_id,
        )
        .options(selectinload(SemanticTable.columns))
        .order_by(SemanticTable.table_name.asc())
    )
    return list(res.scalars().all())


@router.get("/semantic", response_model=SemanticLayerResponse)
async def get_semantic_layer(
    data_source_id: str = Query(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Seed (if needed) then return the semantic layer for a data source."""
    ds_res = await db.execute(
        select(DataSource)
        .where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization.id,
        )
        .options(selectinload(DataSource.tables).selectinload(DataSourceTable.connection_table))
    )
    data_source = ds_res.scalar_one_or_none()
    if data_source is None:
        raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    schema = _enumerate_schema(data_source)

    # Existing semantic rows for this (org, data_source) — columns eager-loaded.
    existing_tables = await _load_semantic_tables(db, str(organization.id), data_source_id)
    # Map table_name -> (semantic_table_id, set(existing column names)). Built from
    # eager-loaded data so we never trigger a sync lazyload under the async session.
    table_id_by_name: dict[str, str] = {}
    cols_by_name: dict[str, set[str]] = {}
    for t in existing_tables:
        table_id_by_name[t.table_name] = t.id
        cols_by_name[t.table_name] = {c.name for c in (t.columns or [])}

    created_any = False
    for table_name, columns in schema:
        sem_table_id = table_id_by_name.get(table_name)
        if sem_table_id is None:
            sem_table = SemanticTable(
                organization_id=str(organization.id),
                data_source_id=data_source_id,
                table_name=table_name,
                description="",
                use_cases=[],
                quality_notes=[],
                status="draft",
            )
            db.add(sem_table)
            await db.flush()
            sem_table_id = sem_table.id
            table_id_by_name[table_name] = sem_table_id
            cols_by_name[table_name] = set()
            created_any = True

        existing_col_names = cols_by_name.get(table_name, set())
        for col in columns:
            if col["name"] in existing_col_names:
                continue
            db.add(SemanticColumn(
                semantic_table_id=sem_table_id,
                name=col["name"],
                type=col["type"],
                meaning="",
                status="draft",
            ))
            existing_col_names.add(col["name"])
            created_any = True

    if created_any:
        await db.commit()

    tables = await _load_semantic_tables(db, str(organization.id), data_source_id)

    total_tables = len(tables)
    total_columns = sum(len(t.columns or []) for t in tables)
    described_tables = sum(1 for t in tables if (t.description or "").strip())
    described_pct = (described_tables / total_tables) if total_tables else 0.0

    return SemanticLayerResponse(
        data_source_id=data_source_id,
        tables=[SemanticTableRead.model_validate(t) for t in tables],
        stats=SemanticLayerStats(
            tables=total_tables,
            columns=total_columns,
            described_pct=described_pct,
        ),
    )


@router.patch("/semantic/table/{table_id}", response_model=SemanticTableRead)
async def patch_semantic_table(
    table_id: str,
    patch: SemanticTablePatch,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    res = await db.execute(
        select(SemanticTable)
        .where(
            SemanticTable.id == table_id,
            SemanticTable.organization_id == organization.id,
        )
        .options(selectinload(SemanticTable.columns))
    )
    sem_table = res.scalar_one_or_none()
    if sem_table is None:
        raise AppError.not_found("semantic.table_not_found", "Semantic table not found")

    data = patch.model_dump(exclude_unset=True)
    if "description" in data and data["description"] is not None:
        sem_table.description = data["description"]
    if "use_cases" in data and data["use_cases"] is not None:
        sem_table.use_cases = data["use_cases"]
    if "quality_notes" in data and data["quality_notes"] is not None:
        sem_table.quality_notes = data["quality_notes"]
    if "status" in data and data["status"] is not None:
        sem_table.status = data["status"]
    # Governance (Kepler Phase 1)
    if "owner" in data and data["owner"] is not None:
        sem_table.owner = data["owner"]
    if "pii" in data and data["pii"] is not None:
        sem_table.pii = bool(data["pii"])
    if "freshness_sla_hours" in data and data["freshness_sla_hours"] is not None:
        sem_table.freshness_sla_hours = data["freshness_sla_hours"]

    await db.commit()
    await db.refresh(sem_table)
    res2 = await db.execute(
        select(SemanticTable)
        .where(SemanticTable.id == table_id)
        .options(selectinload(SemanticTable.columns))
    )
    sem_table = res2.scalar_one()
    return SemanticTableRead.model_validate(sem_table)


@router.patch("/semantic/column/{column_id}", response_model=SemanticColumnRead)
async def patch_semantic_column(
    column_id: str,
    patch: SemanticColumnPatch,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    res = await db.execute(
        select(SemanticColumn)
        .join(SemanticTable, SemanticColumn.semantic_table_id == SemanticTable.id)
        .where(
            SemanticColumn.id == column_id,
            SemanticTable.organization_id == organization.id,
        )
    )
    sem_col = res.scalar_one_or_none()
    if sem_col is None:
        raise AppError.not_found("semantic.column_not_found", "Semantic column not found")

    data = patch.model_dump(exclude_unset=True)
    if "meaning" in data and data["meaning"] is not None:
        sem_col.meaning = data["meaning"]
    if "status" in data and data["status"] is not None:
        sem_col.status = data["status"]
    # Governance (Kepler Phase 1)
    if "pii" in data and data["pii"] is not None:
        sem_col.pii = bool(data["pii"])
    if "sensitivity" in data and data["sensitivity"] is not None:
        sem_col.sensitivity = data["sensitivity"]

    await db.commit()
    await db.refresh(sem_col)
    return SemanticColumnRead.model_validate(sem_col)


# ---------------------------------------------------------------------------
# Phase-1 Metrics Catalog: named business metrics (name -> definition -> SQL)
# ---------------------------------------------------------------------------

import re as _re

# Statements that are NOT read-only. Used to reject anything that mutates.
_WRITE_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "merge", "replace", "call", "exec",
    "execute", "vacuum", "comment", "lock", "set", "begin", "commit",
    "rollback", "savepoint",
)


def _strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments for safe keyword checks."""
    sql = _re.sub(r"/\*.*?\*/", " ", sql, flags=_re.DOTALL)
    sql = _re.sub(r"--[^\n]*", " ", sql)
    return sql


def _is_read_only_sql(sql: str) -> bool:
    """True only for a single read statement starting with SELECT or WITH.

    Rejects multiple statements, any write/DDL keyword, and anything not
    leading with SELECT/WITH.
    """
    if not sql or not sql.strip():
        return False
    cleaned = _strip_sql_comments(sql).strip()
    if not cleaned:
        return False
    # Reject multiple statements (allow a single optional trailing semicolon).
    body = cleaned.rstrip().rstrip(";")
    if ";" in body:
        return False
    lowered = body.lower()
    first = lowered.split(None, 1)[0] if lowered.split(None, 1) else ""
    if first not in ("select", "with"):
        return False
    # Strip "quoted identifiers" + 'string literals' so a column named e.g.
    # "Call Type" doesn't trip the CALL write-keyword (real DML leads with its
    # keyword, already rejected by the SELECT/WITH gate above).
    scan = _re.sub(r'"[^"]*"', " ", lowered)
    scan = _re.sub(r"'[^']*'", " ", scan)
    # Defense-in-depth: reject any write/DDL keyword appearing as a word.
    for kw in _WRITE_KEYWORDS:
        if _re.search(r"\b" + _re.escape(kw) + r"\b", scan):
            return False
    return True


async def _get_metric_or_404(db: AsyncSession, org_id: str, metric_id: str) -> MetricDefinition:
    res = await db.execute(
        select(MetricDefinition).where(
            MetricDefinition.id == metric_id,
            MetricDefinition.organization_id == org_id,
        )
    )
    metric = res.scalar_one_or_none()
    if metric is None:
        raise AppError.not_found("metric.not_found", "Metric not found")
    return metric


@router.get("/metrics", response_model=MetricsResponse)
async def list_metrics(
    data_source_id: str = Query(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List metrics for a data source in the current org, ordered by name."""
    res = await db.execute(
        select(MetricDefinition)
        .where(
            MetricDefinition.organization_id == organization.id,
            MetricDefinition.data_source_id == data_source_id,
        )
        .order_by(MetricDefinition.name.asc())
    )
    metrics = list(res.scalars().all())
    return MetricsResponse(metrics=[MetricRead.model_validate(m) for m in metrics])


@router.post("/metrics", response_model=MetricRead)
async def create_metric(
    payload: MetricCreate,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Create a metric. 409 on duplicate name within the same data source."""
    # Validate the data source belongs to this org.
    ds_res = await db.execute(
        select(DataSource).where(
            DataSource.id == payload.data_source_id,
            DataSource.organization_id == organization.id,
        )
    )
    if ds_res.scalar_one_or_none() is None:
        raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    dup_res = await db.execute(
        select(MetricDefinition).where(
            MetricDefinition.organization_id == organization.id,
            MetricDefinition.data_source_id == payload.data_source_id,
            MetricDefinition.name == payload.name,
        )
    )
    if dup_res.scalar_one_or_none() is not None:
        raise AppError.conflict("metric.duplicate", "A metric with this name already exists for this data source")

    owner = getattr(current_user, "email", None) or str(current_user.id)
    metric = MetricDefinition(
        organization_id=str(organization.id),
        data_source_id=payload.data_source_id,
        name=payload.name,
        definition=payload.definition or "",
        table_ref=payload.table_ref or "",
        sql_calc=payload.sql_calc or "",
        owner=owner,
        status="draft",
    )
    db.add(metric)
    await db.commit()
    await db.refresh(metric)
    return MetricRead.model_validate(metric)


@router.patch("/metrics/{metric_id}", response_model=MetricRead)
async def patch_metric(
    metric_id: str,
    patch: MetricPatch,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    metric = await _get_metric_or_404(db, str(organization.id), metric_id)

    data = patch.model_dump(exclude_unset=True)
    for field in ("name", "definition", "table_ref", "sql_calc", "status"):
        if field in data and data[field] is not None:
            setattr(metric, field, data[field])

    await db.commit()
    await db.refresh(metric)
    return MetricRead.model_validate(metric)


@router.delete("/metrics/{metric_id}")
async def delete_metric(
    metric_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    metric = await _get_metric_or_404(db, str(organization.id), metric_id)
    await db.delete(metric)
    await db.commit()
    return {"ok": True}


@router.post("/metrics/{metric_id}/test", response_model=MetricTestResult)
async def test_metric(
    metric_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Run the metric's sql_calc READ-ONLY against its data source.

    Reuses dash's data-source query path: DataSource.get_client().aexecute_query()
    (returns a pandas DataFrame). Enforces a single read statement and caps the
    returned rows at 100. Execution failures are returned as ok:false / error
    with HTTP 200 — this is a test result, not a server failure.
    """
    metric = await _get_metric_or_404(db, str(organization.id), metric_id)

    sql = (metric.sql_calc or "").strip()
    if not sql:
        return MetricTestResult(ok=False, error="no SQL")

    if not _is_read_only_sql(sql):
        return MetricTestResult(ok=False, error="only a single read-only SELECT/WITH statement is allowed")

    # Load the data source (with connections) to obtain a query client.
    ds_res = await db.execute(
        select(DataSource).where(
            DataSource.id == metric.data_source_id,
            DataSource.organization_id == organization.id,
        )
    )
    data_source = ds_res.scalar_one_or_none()
    if data_source is None:
        return MetricTestResult(ok=False, error="data source not found")

    try:
        client = data_source.get_client()
        df = await client.aexecute_query(sql)
    except Exception as e:  # noqa: BLE001 — surface as a test result, not a 500
        return MetricTestResult(ok=False, error=str(e))

    try:
        columns = [str(c) for c in list(df.columns)]
        total = int(len(df))
        capped = df.head(100)
        rows: list[list] = []
        for _idx, row in capped.iterrows():
            rows.append([_jsonable(v) for v in row.tolist()])
        # Scalar convenience value: single-cell result (e.g. SELECT COUNT(*)).
        value = None
        if total >= 1 and len(columns) == 1:
            value = rows[0][0] if rows else None
        return MetricTestResult(
            ok=True,
            value=value,
            columns=columns,
            rows=rows,
            row_count=total,
        )
    except Exception as e:  # noqa: BLE001
        return MetricTestResult(ok=False, error=f"failed to serialize result: {e}")


def _jsonable(v):
    """Best-effort convert a pandas/numpy cell value to a JSON-serializable type."""
    try:
        import pandas as _pd  # local import; pandas is a hard dep of the clients
        if v is None or (isinstance(v, float) and v != v):  # NaN
            return None
        if _pd.isna(v):
            return None
    except Exception:
        pass
    # numpy scalar -> python scalar
    item = getattr(v, "item", None)
    if callable(item):
        try:
            return v.item()
        except Exception:
            pass
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


# ---------------------------------------------------------------------------
# Phase-3 Query Library: saved, named, proven SQL queries (name -> sql_text)
# ---------------------------------------------------------------------------


async def _get_query_or_404(db: AsyncSession, org_id: str, query_id: str) -> QueryLibraryItem:
    res = await db.execute(
        select(QueryLibraryItem).where(
            QueryLibraryItem.id == query_id,
            QueryLibraryItem.organization_id == org_id,
        )
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise AppError.not_found("query.not_found", "Query not found")
    return item


@router.get("/queries", response_model=QueryLibraryResponse)
async def list_queries(
    data_source_id: str = Query(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List saved queries for a data source in the current org, ordered by name."""
    res = await db.execute(
        select(QueryLibraryItem)
        .where(
            QueryLibraryItem.organization_id == organization.id,
            QueryLibraryItem.data_source_id == data_source_id,
        )
        .order_by(QueryLibraryItem.name.asc())
    )
    items = list(res.scalars().all())
    total = len(items)
    approved = sum(1 for i in items if (i.status or "") == "approved")
    return QueryLibraryResponse(
        data_source_id=data_source_id,
        queries=[QueryItemRead.model_validate(i) for i in items],
        stats={"total": total, "approved": approved},
    )


@router.post("/queries", response_model=QueryItemRead)
async def create_query(
    payload: QueryCreate,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Create a saved query. 409 on duplicate name within the same data source."""
    # Validate the data source belongs to this org.
    ds_res = await db.execute(
        select(DataSource).where(
            DataSource.id == payload.data_source_id,
            DataSource.organization_id == organization.id,
        )
    )
    if ds_res.scalar_one_or_none() is None:
        raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    dup_res = await db.execute(
        select(QueryLibraryItem).where(
            QueryLibraryItem.organization_id == organization.id,
            QueryLibraryItem.data_source_id == payload.data_source_id,
            QueryLibraryItem.name == payload.name,
        )
    )
    if dup_res.scalar_one_or_none() is not None:
        raise AppError.conflict("query.duplicate", "A query with this name already exists for this data source")

    owner = getattr(current_user, "email", None) or str(current_user.id)
    item = QueryLibraryItem(
        organization_id=str(organization.id),
        data_source_id=payload.data_source_id,
        name=payload.name,
        description=payload.description or "",
        sql_text=payload.sql_text or "",
        tags=payload.tags or [],
        source="manual",
        run_count=0,
        owner=owner,
        status="draft",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return QueryItemRead.model_validate(item)


@router.patch("/queries/{query_id}", response_model=QueryItemRead)
async def patch_query(
    query_id: str,
    patch: QueryPatch,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    item = await _get_query_or_404(db, str(organization.id), query_id)

    data = patch.model_dump(exclude_unset=True)
    for field in ("name", "description", "sql_text", "tags", "source", "status"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])

    await db.commit()
    await db.refresh(item)
    return QueryItemRead.model_validate(item)


@router.delete("/queries/{query_id}")
async def delete_query(
    query_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    item = await _get_query_or_404(db, str(organization.id), query_id)
    await db.delete(item)
    await db.commit()
    return {"ok": True}


@router.post("/queries/{query_id}/run", response_model=QueryRunResult)
async def run_query(
    query_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Run a saved query's sql_text READ-ONLY against its data source.

    Reuses the same read-only guard + executor as the metric `/test` endpoint:
    DataSource.get_client().aexecute_query() (returns a pandas DataFrame), a
    single read statement only, capped at 100 returned rows. On a successful run
    the item's `run_count` is incremented. Execution failures return ok:false /
    error with HTTP 200 — a run result, not a server failure.
    """
    item = await _get_query_or_404(db, str(organization.id), query_id)

    sql = (item.sql_text or "").strip()
    if not sql:
        return QueryRunResult(ok=False, error="no SQL")

    if not _is_read_only_sql(sql):
        return QueryRunResult(ok=False, error="only a single read-only SELECT/WITH statement is allowed")

    # Load the data source (with connections) to obtain a query client.
    ds_res = await db.execute(
        select(DataSource).where(
            DataSource.id == item.data_source_id,
            DataSource.organization_id == organization.id,
        )
    )
    data_source = ds_res.scalar_one_or_none()
    if data_source is None:
        return QueryRunResult(ok=False, error="data source not found")

    try:
        client = data_source.get_client()
        df = await client.aexecute_query(sql)
    except Exception as e:  # noqa: BLE001 — surface as a run result, not a 500
        return QueryRunResult(ok=False, error=str(e))

    try:
        columns = [str(c) for c in list(df.columns)]
        total = int(len(df))
        capped = df.head(100)
        rows: list[list] = []
        for _idx, row in capped.iterrows():
            rows.append([_jsonable(v) for v in row.tolist()])
    except Exception as e:  # noqa: BLE001
        return QueryRunResult(ok=False, error=f"failed to serialize result: {e}")

    # Successful run: bump run_count.
    item.run_count = (item.run_count or 0) + 1
    await db.commit()

    return QueryRunResult(
        ok=True,
        columns=columns,
        rows=rows,
        row_count=total,
    )


# ---------------------------------------------------------------------------
# Phase-6 Engineer Assets surfacing: SURFACE existing engineer-built data assets.
#
# Assets are NOT a new model — they are Instruction rows written by
# build_data_asset.py with category=='data_asset' and ai_source=='engineer_asset'.
# This is a read-only projection (+ a status toggle for tab parity). Gated by
# flags.ENGINEER_ASSETS: when OFF we return an empty/zero result (zero-leak).
# Internal/data errors NEVER raise — we degrade to an empty result.
# ---------------------------------------------------------------------------

def _epoch(dt) -> float:
    """Best-effort epoch seconds for ordering; missing/odd values sort oldest."""
    try:
        return dt.timestamp() if dt is not None else float("-inf")
    except Exception:
        return float("-inf")


_ASSET_BOILERPLATE_PREFIX = "Data asset `"


def _asset_description(text: str | None) -> str:
    """Strip the boilerplate first line; return the real description.

    build_data_asset writes:
        "Data asset `obj` (agent-built). Prefer ...\n\n<description>"
    We keep the part AFTER the first blank line. If there is no blank-line split,
    fall back to the full text.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    parts = raw.split("\n\n", 1)
    if len(parts) == 2 and parts[0].startswith(_ASSET_BOILERPLATE_PREFIX):
        return parts[1].strip()
    return raw


def _asset_to_item(inst: Instruction) -> AssetItemRead | None:
    """Map an engineer-asset Instruction row to an AssetItemRead, or None to skip."""
    sd = inst.structured_data if isinstance(inst.structured_data, dict) else {}
    object_name = sd.get("object") or ""
    if not object_name:
        return None
    name = object_name.split(".")[-1] if "." in object_name else object_name
    kind = sd.get("kind") or "view"
    status = "approved" if inst.status == "published" else (inst.status or "draft")
    return AssetItemRead(
        id=str(inst.id),
        name=name,
        object_name=object_name,
        kind=kind,
        description=_asset_description(inst.text),
        status=status,
        source=inst.ai_source or "engineer_asset",
        created_at=getattr(inst, "created_at", None),
        updated_at=getattr(inst, "updated_at", None),
    )


@router.get("/assets", response_model=AssetsResponse)
async def list_assets(
    data_source_id: str | None = Query(default=None),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Surface engineer-built data assets (Instruction rows) for the org.

    Flag-gated by ``flags.ENGINEER_ASSETS`` — OFF returns an empty/zero result.
    ``data_source_id`` is optional and currently echoed back only (assets carry no
    per-source link). Data issues degrade to an empty result; we never 500.
    """
    if not flags.ENGINEER_ASSETS:
        return AssetsResponse(data_source_id=data_source_id, assets=[], stats={"total": 0, "approved": 0})

    items: list[AssetItemRead] = []
    try:
        res = await db.execute(
            select(Instruction)
            .where(
                Instruction.organization_id == str(organization.id),
                Instruction.category == "data_asset",
                Instruction.ai_source == "engineer_asset",
            )
            .order_by(Instruction.created_at.desc())
        )
        for inst in res.scalars().all():
            item = _asset_to_item(inst)
            if item is not None:
                items.append(item)
        # Newest-first by created_at; fall back to name asc when missing/tied.
        # Use a (epoch, name) sort key so naive/aware datetimes never collide.
        items.sort(key=lambda a: (-_epoch(a.created_at), (a.name or "").lower()))
    except Exception:  # noqa: BLE001 — never surface a data issue to the client
        return AssetsResponse(data_source_id=data_source_id, assets=[], stats={"total": 0, "approved": 0})

    total = len(items)
    approved = sum(1 for a in items if a.status == "approved")
    return AssetsResponse(
        data_source_id=data_source_id,
        assets=items,
        stats={"total": total, "approved": approved},
    )


async def _get_asset_or_404(db: AsyncSession, org_id: str, asset_id: str) -> Instruction:
    res = await db.execute(
        select(Instruction).where(
            Instruction.id == asset_id,
            Instruction.organization_id == org_id,
            Instruction.category == "data_asset",
        )
    )
    inst = res.scalar_one_or_none()
    if inst is None:
        raise AppError.not_found("asset.not_found", "Data asset not found")
    return inst


@router.post("/assets/{id}/approve")
async def approve_asset(
    id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Approve an engineer asset -> Instruction.status='published' (live/approved)."""
    inst = await _get_asset_or_404(db, str(organization.id), id)
    inst.status = "published"
    await db.commit()
    return {"ok": True}


@router.post("/assets/{id}/reject")
async def reject_asset(
    id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Reject an engineer asset -> Instruction.status='draft' (hidden from live)."""
    inst = await _get_asset_or_404(db, str(organization.id), id)
    inst.status = "draft"
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Phase-5 self-learning write-back: review queue for AI-proposed knowledge.
#
# The knowledge proposer (app/ai/brain/knowledge_proposer.py) writes
# status='pending' rows on SemanticTable / MetricDefinition when a user 👎s an
# answer (gated). QueryLibraryItem can also carry pending rows (promoted query
# proposals). These endpoints let the UI list and approve/reject those proposals.
# Phase-4 context builders inject ONLY status=='approved', so pending rows never
# reach the agent until approved here. Reject is SOFT (status='rejected', kept
# for audit) — never a hard delete.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase-7 "AI-suggest": introspect a data source's schema and let the LLM
# PROPOSE pending knowledge (semantic table descriptions + candidate metrics).
# Proposals land as status='pending' rows (via the Phase-5 write helpers) so
# they appear in the existing Review tab for approval. Flag-gated by
# SEMANTIC_LAYER / METRICS_CATALOG (zero-leak + no LLM call when both OFF).
# Data/LLM issues degrade to an empty result; only a missing data source 404s.
# Literal-first path /ai-suggest/{data_source_id} avoids shadowing the literal
# routes (/metrics /queries /assets /semantic /pending) and the /{kind}/... ones.
# ---------------------------------------------------------------------------


@router.post("/ai-suggest/{data_source_id}")
async def ai_suggest_knowledge(
    data_source_id: str,
    body: dict | None = Body(default=None),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """AI-suggest pending knowledge from a data source's schema.

    Body (optional): {"focus": "semantic"|"metrics"|"both"} (default "both").
    Returns the ids of the proposed (pending) rows + counts. Both flags OFF ->
    a disabled, zero-leak result with NO LLM call and NO data-source lookup.
    """
    # Flag gate FIRST (short-circuits before the data-source lookup): if neither
    # the semantic layer nor the metrics catalog is enabled, do nothing.
    if not (flags.SEMANTIC_LAYER or flags.METRICS_CATALOG):
        return {
            "proposed": {"semantics": [], "metrics": []},
            "counts": {"semantics": 0, "metrics": 0},
            "disabled": True,
        }

    focus = "both"
    if isinstance(body, dict):
        raw_focus = body.get("focus")
        if raw_focus in ("semantic", "metrics", "both"):
            focus = raw_focus

    # Fetch the data source, org-scoped (with connections, like /test and /run).
    ds_res = await db.execute(
        select(DataSource)
        .where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization.id,
        )
        .options(selectinload(DataSource.tables).selectinload(DataSourceTable.connection_table))
    )
    data_source = ds_res.scalar_one_or_none()
    if data_source is None:
        raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    # Resolve the org's small model the same way the Phase-5 worker does.
    from app.services.llm_service import LLMService
    model = await LLMService().get_default_model(db, organization, current_user, is_small=True)

    from app.ai.brain.knowledge_proposer import propose_knowledge_from_schema
    result = await propose_knowledge_from_schema(
        db,
        organization=organization,
        data_source=data_source,
        model=model,
        focus=focus,
    )

    semantics = result.get("semantics", []) if isinstance(result, dict) else []
    metrics = result.get("metrics", []) if isinstance(result, dict) else []
    return {
        "proposed": {"semantics": semantics, "metrics": metrics},
        "counts": {"semantics": len(semantics), "metrics": len(metrics)},
        "disabled": False,
    }


@router.post("/ai-suggest-columns/{data_source_id}")
async def ai_suggest_columns(
    data_source_id: str,
    body: dict | None = Body(default=None),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """AI-suggest per-column semantic meanings from a data source's schema.

    Returns the ids of the proposed (pending) column rows + counts. SEMANTIC_LAYER
    OFF -> a disabled, zero-leak result with NO LLM call and NO data-source lookup.
    Body is ignored (columns has no focus).
    """
    # Flag gate FIRST (short-circuits before the data-source lookup): if the
    # semantic layer is not enabled, do nothing.
    if not flags.SEMANTIC_LAYER:
        return {
            "disabled": True,
            "proposed": {"columns": []},
            "counts": {"columns": 0},
        }

    # Fetch the data source, org-scoped (same select/where as /ai-suggest).
    ds_res = await db.execute(
        select(DataSource)
        .where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization.id,
        )
        .options(selectinload(DataSource.tables).selectinload(DataSourceTable.connection_table))
    )
    data_source = ds_res.scalar_one_or_none()
    if data_source is None:
        raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    # Resolve the org's small model the same way the Phase-5 worker does.
    from app.services.llm_service import LLMService
    model = await LLMService().get_default_model(db, organization, current_user, is_small=True)

    # Fail-soft: data/LLM issues degrade to an empty result; never 500.
    try:
        from app.ai.brain.knowledge_proposer import propose_column_meanings
        result = await propose_column_meanings(
            db,
            organization=organization,
            data_source=data_source,
            model=model,
        )
    except Exception:
        result = {"columns": []}

    if not isinstance(result, dict):
        result = {"columns": []}
    columns = result.get("columns", [])
    return {
        "proposed": result,
        "counts": {"columns": len(columns)},
        "disabled": False,
    }


_PENDING_KINDS = ("semantic", "metric", "query")


def _iso(dt) -> str | None:
    try:
        return dt.isoformat() if dt is not None else None
    except Exception:
        return None


def _provenance(owner: str | None, source: str | None) -> str | None:
    """Short human-readable origin for a pending proposal. Never raises."""
    try:
        if owner == "ai-memory-loop":
            return "\U0001F44D from chat"
        if owner == "ai-distiller":
            return "\U0001F44E distilled"
        if source == "chat":
            return "from chat"
    except Exception:
        pass
    return None


@router.get("/pending")
async def list_pending_knowledge(
    type: str | None = Query(default=None),
    data_source_id: str | None = Query(default=None),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List pending (AI-proposed) knowledge rows for the org, ready for review.

    Optional ``?type=semantic|metric|query`` filters to one kind; optional
    ``?data_source_id=`` scopes to one data source. Returns each item tagged with
    its ``type`` plus enough to render it, and a stats breakdown.
    """
    if type is not None and type not in _PENDING_KINDS:
        raise AppError.bad_request(ErrorCode.VALIDATION, f"type must be one of {_PENDING_KINDS}")

    org_id = str(organization.id)
    proposals: list[dict] = []
    stats = {"semantic": 0, "metric": 0, "query": 0, "total": 0}

    if type in (None, "semantic"):
        stmt = (
            select(SemanticTable)
            .where(
                SemanticTable.organization_id == org_id,
                SemanticTable.status == "pending",
            )
            .order_by(SemanticTable.created_at.desc())
        )
        if data_source_id:
            stmt = stmt.where(SemanticTable.data_source_id == data_source_id)
        for r in (await db.execute(stmt)).scalars().all():
            proposals.append({
                "id": r.id,
                "type": "semantic",
                "name": r.table_name,
                "table_name": r.table_name,
                "description": r.description or "",
                "definition": None,
                "sql": None,
                "data_source_id": r.data_source_id,
                "created_at": _iso(r.created_at),
                "source": None,
                "owner": getattr(r, "owner", None),
                "provenance": _provenance(getattr(r, "owner", None), None),
            })
            stats["semantic"] += 1

    if type in (None, "metric"):
        stmt = (
            select(MetricDefinition)
            .where(
                MetricDefinition.organization_id == org_id,
                MetricDefinition.status == "pending",
            )
            .order_by(MetricDefinition.created_at.desc())
        )
        if data_source_id:
            stmt = stmt.where(MetricDefinition.data_source_id == data_source_id)
        for r in (await db.execute(stmt)).scalars().all():
            proposals.append({
                "id": r.id,
                "type": "metric",
                "name": r.name,
                "table_name": r.table_ref or None,
                "description": r.definition or "",
                "definition": r.definition or "",
                "sql": r.sql_calc or "",
                "data_source_id": r.data_source_id,
                "created_at": _iso(r.created_at),
                "source": None,
                "owner": getattr(r, "owner", None),
                "provenance": _provenance(getattr(r, "owner", None), None),
            })
            stats["metric"] += 1

    if type in (None, "query"):
        stmt = (
            select(QueryLibraryItem)
            .where(
                QueryLibraryItem.organization_id == org_id,
                QueryLibraryItem.status == "pending",
            )
            .order_by(QueryLibraryItem.created_at.desc())
        )
        if data_source_id:
            stmt = stmt.where(QueryLibraryItem.data_source_id == data_source_id)
        for r in (await db.execute(stmt)).scalars().all():
            proposals.append({
                "id": r.id,
                "type": "query",
                "name": r.name,
                "table_name": None,
                "description": r.description or "",
                "definition": None,
                "sql": r.sql_text or "",
                "data_source_id": r.data_source_id,
                "created_at": _iso(r.created_at),
                "source": getattr(r, "source", None),
                "owner": getattr(r, "owner", None),
                "provenance": _provenance(getattr(r, "owner", None), getattr(r, "source", None)),
            })
            stats["query"] += 1

    stats["total"] = stats["semantic"] + stats["metric"] + stats["query"]
    return {"proposals": proposals, "stats": stats}


_KIND_MODEL = {
    "semantic": SemanticTable,
    "metric": MetricDefinition,
    "query": QueryLibraryItem,
    "join": TableEdge,
    "doc": KnowledgeDoc,
}


async def _get_pending_row_or_404(db: AsyncSession, org_id: str, kind: str, row_id: str):
    if kind not in _KIND_MODEL:
        raise AppError.bad_request(ErrorCode.VALIDATION, f"kind must be one of {_PENDING_KINDS}")
    model = _KIND_MODEL[kind]
    res = await db.execute(
        select(model).where(
            model.id == row_id,
            model.organization_id == org_id,
        )
    )
    row = res.scalar_one_or_none()
    if row is None:
        raise AppError.not_found("knowledge.proposal_not_found", "Knowledge proposal not found")
    return row


# ---------------------------------------------------------------------------
# Phase-6 JOIN GRAPH: learned join/lineage edges between tables. Mined edges
# land status='pending'; only 'approved' edges surface to the agent. Flag-gated
# by ``flags.JOIN_GRAPH`` — OFF returns an empty/zero result (zero-leak), no DB
# hit. Literal-first paths /joins, /joins/mine are registered BEFORE the
# /{kind}/{id}/... catch-all below (mirrors the /assets and /ai-suggest ordering
# at ~line 870) so 'joins' is never treated as a pending-kind. The catch-all
# approve/reject also handles kind=='join' via the _KIND_MODEL map.
# ---------------------------------------------------------------------------


@router.get("/joins")
async def list_joins(
    data_source_id: str = Query(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List learned join edges for an org+data source (incl. ds-null org-wide
    rows), ordered by ``join_count`` desc. Flag-gated by ``flags.JOIN_GRAPH`` —
    OFF returns an empty/zero result (zero-leak)."""
    if not flags.JOIN_GRAPH:
        return {
            "data_source_id": data_source_id,
            "edges": [],
            "stats": {"total": 0, "approved": 0, "pending": 0},
        }

    from sqlalchemy import or_
    res = await db.execute(
        select(TableEdge)
        .where(
            TableEdge.organization_id == str(organization.id),
            or_(
                TableEdge.data_source_id == data_source_id,
                TableEdge.data_source_id.is_(None),
            ),
        )
        .order_by(TableEdge.join_count.desc())
    )
    rows = list(res.scalars().all())
    edges = [
        {
            "id": e.id,
            "left_table": e.left_table,
            "left_col": e.left_col,
            "right_table": e.right_table,
            "right_col": e.right_col,
            "join_count": e.join_count or 0,
            "confidence": e.confidence or 0.0,
            "source": e.source,
            "status": e.status,
        }
        for e in rows
    ]
    total = len(edges)
    approved = sum(1 for e in edges if e["status"] == "approved")
    pending = sum(1 for e in edges if e["status"] == "pending")
    return {
        "data_source_id": data_source_id,
        "edges": edges,
        "stats": {"total": total, "approved": approved, "pending": pending},
    }


@router.post("/joins/mine")
async def mine_joins(
    body: dict = Body(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Mine join edges from proven SQL for a data source -> pending TableEdge rows.

    Body: ``{"data_source_id": str}``. Flag-gated by ``flags.JOIN_GRAPH`` (OFF ->
    ``{disabled:true, mined:0}``, no work). Validates the DS belongs to the org
    (mirrors the /metrics POST). Fail-soft: any error -> HTTP 200 ``{mined:0,
    error:...}`` rather than a 500."""
    if not flags.JOIN_GRAPH:
        return {"disabled": True, "mined": 0}

    data_source_id = (body or {}).get("data_source_id")
    if not data_source_id:
        return {"mined": 0, "error": "data_source_id required"}

    ds_res = await db.execute(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization.id,
        )
    )
    if ds_res.scalar_one_or_none() is None:
        raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    try:
        from app.ai.knowledge.join_miner import mine_join_edges
        count = await mine_join_edges(
            db, organization=organization, data_source_id=data_source_id
        )
        return {"mined": count}
    except Exception as e:  # noqa: BLE001 — surface as a result, not a 500
        logger.exception("join mine failed")
        return {"mined": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# Phase-5 DOCS RAG: unstructured knowledge docs (pasted text / imported) chunked
# + indexed for retrieval. Ingested docs land status='pending'; only 'approved'
# docs + their chunks reach the agent (same approval invariant as the other
# kinds). Flag-gated by ``flags.DOC_KNOWLEDGE`` — OFF returns an empty/zero
# result (zero-leak), no work. Literal-first paths /docs, /docs/search are
# registered BEFORE the /{kind}/{id}/... catch-all below (mirrors the /joins,
# /assets, /ai-suggest ordering) so 'docs' is never treated as a pending-kind.
# The catch-all approve/reject also handles kind=='doc' via the _KIND_MODEL map.
# ---------------------------------------------------------------------------


@router.get("/docs")
async def list_docs(
    data_source_id: str | None = Query(None),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List knowledge docs for the org (optionally scoped to a data source, also
    including org-wide ds-null docs), newest first. Flag-gated by
    ``flags.DOC_KNOWLEDGE`` — OFF returns an empty/zero result (zero-leak)."""
    if not flags.DOC_KNOWLEDGE:
        return {"docs": [], "stats": {"total": 0, "approved": 0, "pending": 0}}

    from sqlalchemy import or_
    stmt = (
        select(KnowledgeDoc)
        .where(
            KnowledgeDoc.organization_id == str(organization.id),
            KnowledgeDoc.deleted_at.is_(None),
        )
        .options(selectinload(KnowledgeDoc.chunks))
        .order_by(KnowledgeDoc.created_at.desc())
    )
    if data_source_id:
        stmt = stmt.where(
            or_(
                KnowledgeDoc.data_source_id == data_source_id,
                KnowledgeDoc.data_source_id.is_(None),
            )
        )
    rows = list((await db.execute(stmt)).scalars().all())
    docs = [
        {
            "id": d.id,
            "title": d.title,
            "source": d.source,
            "status": d.status,
            "url": d.url,
            "data_source_id": d.data_source_id,
            "chunks": len(d.chunks or []),
            "created_at": _iso(d.created_at),
        }
        for d in rows
    ]
    total = len(docs)
    approved = sum(1 for d in docs if d["status"] == "approved")
    pending = sum(1 for d in docs if d["status"] == "pending")
    return {"docs": docs, "stats": {"total": total, "approved": approved, "pending": pending}}


@router.post("/docs")
async def create_doc(
    body: dict = Body(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Ingest a knowledge doc -> chunked + indexed pending KnowledgeDoc.

    Body: ``{title, body, source='paste', data_source_id?, url?}``. Flag-gated by
    ``flags.DOC_KNOWLEDGE`` (OFF -> ``{disabled:true}``, no work). 400 on empty
    title/body; if ``data_source_id`` is given it must belong to the org (404 —
    mirrors the /joins/mine + /metrics POST validation). Fail-soft: any error ->
    HTTP 200 ``{error:..., doc_id:None}`` rather than a 500."""
    if not flags.DOC_KNOWLEDGE:
        return {"disabled": True}

    body = body or {}
    title = (body.get("title") or "").strip()
    doc_body = (body.get("body") or "").strip()
    if not title or not doc_body:
        raise AppError.bad_request(ErrorCode.VALIDATION, "title and body are required")

    source = (body.get("source") or "paste").strip() or "paste"
    data_source_id = body.get("data_source_id")
    url = body.get("url")

    if data_source_id:
        ds_res = await db.execute(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.organization_id == organization.id,
            )
        )
        if ds_res.scalar_one_or_none() is None:
            raise AppError.not_found(ErrorCode.DATA_SOURCE_NOT_FOUND, "Data source not found")

    try:
        result = await ingest_doc(
            db,
            organization=organization,
            title=title,
            body=doc_body,
            source=source,
            data_source_id=data_source_id,
            url=url,
        )
        return result
    except Exception as e:  # noqa: BLE001 — surface as a result, not a 500
        logger.exception("doc ingest failed")
        return {"error": str(e), "doc_id": None}


@router.post("/docs/search")
async def search_docs_endpoint(
    body: dict = Body(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Debug endpoint: retrieve top doc chunks for a query. Body: ``{q,
    data_source_id?}``. Flag-gated by ``flags.DOC_KNOWLEDGE`` (OFF -> empty).
    Fail-soft: any error -> ``{results: []}`` rather than a 500."""
    if not flags.DOC_KNOWLEDGE:
        return {"results": []}

    body = body or {}
    q = (body.get("q") or "").strip()
    data_source_id = body.get("data_source_id")
    try:
        rows = await search_docs(
            db,
            organization=organization,
            query=q,
            data_source_id=data_source_id,
            k=8,
        )
        return {"results": rows}
    except Exception:  # noqa: BLE001 — never surface a data issue to the client
        logger.exception("doc search failed")
        return {"results": []}


@router.post("/{kind}/{id}/approve")
async def approve_knowledge(
    kind: str,
    id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Approve a proposed knowledge row -> status='approved' (now agent-visible)."""
    row = await _get_pending_row_or_404(db, str(organization.id), kind, id)

    # Bi-temporal (HYBRID_BITEMPORAL): re-approving a metric/semantic-table
    # supersedes the PRIOR current approved version for the same logical key
    # (invalidates it + links superseded_by) so the "one approved current row
    # per key" partial-unique invariant holds. This MUST run BEFORE flipping
    # `row` to approved — otherwise two approved current rows would coexist at
    # commit time and collide on uq_metric_def_current / uq_semantic_current.
    # The helper filters status=='approved' and id!=keep_id, so it leaves the
    # still-pending `row` untouched. Fail-soft: no-op when the flag is OFF and
    # never raises.
    try:
        from sqlalchemy import func as _func
        from app.ai.brain import bitemporal
        if kind == "metric":
            await bitemporal.supersede_prior(
                db,
                MetricDefinition,
                key_filters=[
                    MetricDefinition.organization_id == row.organization_id,
                    MetricDefinition.data_source_id == row.data_source_id,
                    _func.lower(MetricDefinition.name) == (row.name or "").lower(),
                    MetricDefinition.status == "approved",
                ],
                keep_id=row.id,
            )
        elif kind == "semantic":
            await bitemporal.supersede_prior(
                db,
                SemanticTable,
                key_filters=[
                    SemanticTable.organization_id == row.organization_id,
                    SemanticTable.data_source_id == row.data_source_id,
                    _func.lower(SemanticTable.table_name) == (row.table_name or "").lower(),
                    SemanticTable.status == "approved",
                ],
                keep_id=row.id,
            )
    except Exception:
        logger.exception("bitemporal supersede_prior on approve failed")

    row.status = "approved"
    await db.commit()

    # Phase 4: knowledge change -> fire a context_change eval run for this DS's goldens
    try:
        if flags.EVAL_HARNESS:
            ds_id = getattr(row, "data_source_id", None)
            if ds_id:
                from app.services.eval_harness import enqueue_context_change_run
                await enqueue_context_change_run(
                    db, organization=organization, user=current_user, data_source_id=str(ds_id)
                )
    except Exception:
        logger.exception("phase4 context_change enqueue failed")
    return {"ok": True, "id": id, "kind": kind, "status": "approved"}


@router.post("/{kind}/{id}/reject")
async def reject_knowledge(
    kind: str,
    id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Reject a proposed knowledge row -> status='rejected' (SOFT; kept for audit)."""
    row = await _get_pending_row_or_404(db, str(organization.id), kind, id)
    row.status = "rejected"
    await db.commit()
    return {"ok": True, "id": id, "kind": kind, "status": "rejected"}


@router.get("/context-scope")
async def context_scope(
    data_source_ids: str = Query("", description="Comma-separated data source ids in scope"),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """How much approved Knowledge is grounding the agent for these data sources,
    and how much is injected after the bounded-context top-K cap (arXiv:2605.22502).

    Returns totals + per-question caps so the UI can show "Grounded on N of M
    tables". Counts respect the same flags as the context builders: semantic
    counts are 0 when SEMANTIC_LAYER is OFF, metric counts 0 when METRICS_CATALOG
    is OFF. Never raises — degrades to zeros."""
    import os
    ids = [x for x in (data_source_ids or "").split(",") if x.strip()]
    out = {
        "tables_total": 0, "tables_injected": 0, "tables_cap": 0,
        "metrics_total": 0, "metrics_injected": 0, "metrics_cap": 0,
    }
    if not ids:
        return out
    try:
        sem_cap = int(os.getenv("HYBRID_SEMANTIC_TOP_K", "12") or 12)
        met_cap = int(os.getenv("HYBRID_METRICS_TOP_K", "12") or 12)
    except Exception:
        sem_cap, met_cap = 12, 12

    if flags.SEMANTIC_LAYER:
        try:
            rows = (await db.execute(
                select(SemanticTable.id)
                .where(SemanticTable.organization_id == str(organization.id))
                .where(SemanticTable.data_source_id.in_(ids))
                .where(SemanticTable.status == "approved")
            )).scalars().all()
            t = len(rows)
            out["tables_total"] = t
            out["tables_cap"] = sem_cap
            out["tables_injected"] = min(sem_cap, t)
        except Exception:
            pass

    if flags.METRICS_CATALOG:
        try:
            rows = (await db.execute(
                select(MetricDefinition.id)
                .where(MetricDefinition.organization_id == str(organization.id))
                .where(MetricDefinition.data_source_id.in_(ids))
                .where(MetricDefinition.status == "approved")
            )).scalars().all()
            m = len(rows)
            out["metrics_total"] = m
            out["metrics_cap"] = met_cap
            out["metrics_injected"] = min(met_cap, m)
        except Exception:
            pass

    return out


@router.get("/governance/{data_source_id}")
async def governance_rollup(
    data_source_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Governance summary for a data source (Kepler Phase 1): counts of stale /
    PII / unowned approved semantic tables, plus data-as-of (latest sync). Never
    raises — degrades to zeros."""
    from datetime import datetime, timezone, timedelta
    out = {"tables": 0, "stale": 0, "pii": 0, "unowned": 0, "data_as_of": None}
    try:
        ds = (await db.execute(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.organization_id == str(organization.id),
            )
        )).scalar_one_or_none()
        synced = getattr(ds, "last_synced_at", None) if ds else None

        rows = list((await db.execute(
            select(SemanticTable)
            .where(SemanticTable.organization_id == str(organization.id))
            .where(SemanticTable.data_source_id == data_source_id)
            .where(SemanticTable.status == "approved")
        )).scalars().all())
        out["tables"] = len(rows)
        now = datetime.now(timezone.utc)
        for t in rows:
            if t.pii:
                out["pii"] += 1
            if not (t.owner and str(t.owner).strip()):
                out["unowned"] += 1
            refreshed = t.last_refreshed_at or synced
            sla = t.freshness_sla_hours
            if refreshed and sla:
                ref = refreshed if refreshed.tzinfo else refreshed.replace(tzinfo=timezone.utc)
                if now - ref > timedelta(hours=int(sla)):
                    out["stale"] += 1
        out["data_as_of"] = synced.isoformat() if synced else None
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Hybrid Search index — build/refresh + status (flag: SEMANTIC_SEARCH)
# ---------------------------------------------------------------------------
@router.get("/search-index/status")
async def search_index_status(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Return whether Hybrid Search is enabled + how many rows are indexed."""
    from app.settings.hybrid_flags import flags
    from app.ai.knowledge.indexer import index_count
    from app.ai.knowledge.embeddings import EMBED_MODEL
    org_id = str(organization.id)
    return {
        "enabled": bool(flags.SEMANTIC_SEARCH),
        "indexed": await index_count(db, org_id),
        "embed_model": EMBED_MODEL,
    }


@router.post("/reindex")
async def rebuild_search_index(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Rebuild the Hybrid Search index for this org (FTS + embeddings).

    Flag-gated: returns disabled when SEMANTIC_SEARCH is off. Embeddings use the
    org's existing OpenRouter key (text-embedding-3-small); without a key only
    the full-text index is built.
    """
    from app.settings.hybrid_flags import flags
    if not flags.SEMANTIC_SEARCH:
        return {"disabled": True, "indexed": 0, "embedded": 0}
    from app.ai.knowledge.indexer import reindex_org
    try:
        summary = await reindex_org(db, organization)
    except Exception as exc:
        logger.warning("reindex failed: %s", exc)
        raise AppError(ErrorCode.INTERNAL, "Failed to rebuild search index", status_code=500)
    return summary
