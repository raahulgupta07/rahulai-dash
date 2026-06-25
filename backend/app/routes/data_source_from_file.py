"""POST /api/data_sources/from-file — turn an uploaded Excel/CSV into a Data Agent.

Takes an existing File (uploaded via POST /api/files), creates a `spreadsheet`
Connection + DataSource backed by an in-memory DuckDB engine, runs schema
discovery so each sheet/CSV becomes a queryable table, and returns the created
DataSource (same shape as POST /api/data_sources) plus its discovered tables[].

Schema discovery is fail-soft: if the file can't be read the data source is
still returned (with empty tables[]) rather than crashing the request — except
when the file itself is missing/unreadable up front, which is a 400.
"""

import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import current_user
from app.core.permissions_decorator import requires_permission
from app.dependencies import get_async_db, get_current_organization
from app.models.connection import Connection
from app.models.data_source import DataSource
from app.models.domain_connection import domain_connection
from app.models.file import File as FileModel
from app.models.organization import Organization
from app.models.user import User
from app.services.data_source_service import DataSourceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data_sources"])
data_source_service = DataSourceService()


class DataSourceFromFileRequest(BaseModel):
    file_id: str
    data_source_name: Optional[str] = None
    sheet_names: Optional[List[str]] = None
    description: Optional[str] = None


async def _dedupe_ds_name(db: AsyncSession, org_id: str, base: str) -> str:
    """Return a DataSource name unique within the org: ``base`` if free, else
    ``base (2)``, ``base (3)`` … (org-scoped, case-insensitive). Fail-soft: on any
    query error just return ``base`` and let the insert's 409 guard handle it."""
    try:
        rows = (
            await db.execute(
                select(DataSource.name).where(
                    DataSource.organization_id == org_id,
                    func.lower(DataSource.name).like(func.lower(base) + "%"),
                )
            )
        ).scalars().all()
        taken = {str(n).strip().lower() for n in rows if n}
        if base.lower() not in taken:
            return base
        for i in range(2, 1000):
            cand = f"{base} ({i})"
            if cand.lower() not in taken:
                return cand
    except Exception:  # noqa: BLE001 - never block the upload on the dedupe probe
        pass
    return base


def _resolve_upload_path(stored_path: str) -> Optional[str]:
    """Resolve the on-disk absolute path for an uploaded file, traversal-safe.

    Uploaded files live flat under <cwd>/uploads/files/<basename> (see
    routes/file.py). Returns the path if it exists, else None.
    """
    if not stored_path:
        return None
    base = os.path.basename(stored_path)
    candidate = os.path.join(os.getcwd(), "uploads", "files", base)
    if os.path.exists(candidate):
        return candidate
    rel = os.path.join(os.getcwd(), stored_path)
    if os.path.exists(rel):
        return rel
    if os.path.isabs(stored_path) and os.path.exists(stored_path):
        return stored_path
    return None


async def _new_source_response(db, data_source_service, ds_id, organization, current_user, *, extra=None):
    """Build the standard from-file response body for an existing data source."""
    ds_schema = await data_source_service.get_data_source(db, str(ds_id), organization, current_user)
    try:
        tables = await data_source_service.get_data_source_schema(
            db, str(ds_id), include_inactive=True,
            organization=organization, current_user=current_user,
        )
    except Exception:  # noqa: BLE001
        tables = []
    body = json.loads(ds_schema.json()) if hasattr(ds_schema, "json") else dict(ds_schema)
    body["tables"] = [json.loads(t.json()) if hasattr(t, "json") else dict(t) for t in (tables or [])]
    if extra:
        body.update(extra)
    return body


async def _spreadsheet_connections(db, org_id):
    """All non-deleted spreadsheet Connections for the org, eagerly mapped to
    their (single) DataSource. Returns list[(Connection, DataSource)]."""
    rows = (
        await db.execute(
            select(Connection)
            .options(selectinload(Connection.data_sources))
            .where(
                Connection.organization_id == org_id,
                Connection.type == "spreadsheet",
                Connection.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    out = []
    for c in rows:
        ds = (c.data_sources[0] if getattr(c, "data_sources", None) else None)
        if ds is not None and ds.deleted_at is None:
            out.append((c, ds))
    return out


async def _try_merge_same_schema(db, *, organization, current_user, file, abs_path, content_hash):
    """Task 5: return a response body when this upload should reuse an existing
    source (byte-identical dedup OR same-schema append), else None to fall back.

    Defensive throughout — any failure returns None so the caller creates a new
    source as today.
    """
    from app.services.ingest import smart_upload
    from app.data_sources.clients.spreadsheet_client import SpreadsheetClient
    from sqlalchemy.orm.attributes import flag_modified

    candidates = await _spreadsheet_connections(db, str(organization.id))
    if not candidates:
        return None

    # ── (a) content-hash dedup: byte-identical re-upload -> point to existing ──
    for conn, ds in candidates:
        try:
            cfg = json.loads(conn.config) if isinstance(conn.config, str) else (conn.config or {})
        except Exception:  # noqa: BLE001
            cfg = {}
        if cfg.get("content_hash") and cfg.get("content_hash") == content_hash:
            logger.info("from-file: dedup hit -> reuse data_source %s (hash %s)", ds.id, content_hash[:12])
            return await _new_source_response(
                db, data_source_service, ds.id, organization, current_user,
                extra={"reused": True, "merged": False, "reason": "content_hash_dedup"},
            )

    # ── (b) same-schema append: match normalized column-set of sheet(s) ────────
    try:
        new_frames = SpreadsheetClient(path=file.path, file_id=str(file.id))._load_frames()
    except Exception:  # noqa: BLE001
        return None
    if not new_frames:
        return None
    new_colsets = {name: smart_upload.normalize_columns(df.columns) for name, df in new_frames.items()}

    for conn, ds in candidates:
        try:
            cfg = json.loads(conn.config) if isinstance(conn.config, str) else (conn.config or {})
            existing = SpreadsheetClient(
                path=cfg.get("path"),
                sheet_names=cfg.get("sheet_names"),
                file_id=cfg.get("file_id"),
                merged_paths=cfg.get("merged_paths"),
            )._load_frames()
        except Exception:  # noqa: BLE001
            continue
        existing_colsets = {name: smart_upload.normalize_columns(df.columns) for name, df in existing.items()}

        # Every NEW sheet must match SOME existing sheet exactly (conservative).
        all_match = bool(new_colsets) and all(
            any(smart_upload.columns_match(ncs, ecs) for ecs in existing_colsets.values())
            for ncs in new_colsets.values()
        )
        if not all_match:
            continue

        # Append: add this file to the target source's merged_paths + re-sync.
        label = smart_upload.label_from_filename(file.filename or file.path)
        mp = list(cfg.get("merged_paths") or [])
        mp.append({"path": file.path, "label": label, "file_id": str(file.id)})
        cfg["merged_paths"] = mp
        conn.config = json.dumps(cfg) if isinstance(conn.config, str) else cfg
        flag_modified(conn, "config")
        await db.commit()

        # Re-run schema discovery so row counts/profiling reflect the merged data.
        try:
            from app.services.connection_service import ConnectionService

            ds_q = await db.execute(
                select(DataSource).options(selectinload(DataSource.connections)).filter(DataSource.id == ds.id)
            )
            ds_full = ds_q.scalar_one()
            conn_full = ds_full.connections[0]
            await ConnectionService().refresh_schema(db=db, connection=conn_full, current_user=current_user)
            await data_source_service.sync_domain_tables_from_connection(
                db=db, data_source=ds_full, connection=conn_full, max_auto_select=9999,
            )
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.warning("from-file: re-sync after same-schema append failed", exc_info=True)
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass

        logger.info("from-file: same-schema append -> data_source %s (+%s)", ds.id, label)
        return await _new_source_response(
            db, data_source_service, ds.id, organization, current_user,
            extra={"reused": True, "merged": True, "reason": "same_schema_append", "appended_label": label},
        )

    return None


async def _route_glossary_sheets(db, *, organization, data_source, file, abs_path):
    """Task 6: detect glossary/data-dictionary sheets in the file, ingest each
    into the Knowledge layer (KnowledgeDoc, pending), and deactivate the
    corresponding junk queryable table. Returns the list of routed sheet names.

    Conservative + fail-soft: only confident glossary sheets are routed; a sheet
    that also reads as a real table stays queryable unless it's confidently a
    glossary. Never raises into the caller.
    """
    from app.services.ingest import smart_upload
    from app.data_sources.clients.spreadsheet_client import SpreadsheetClient
    from app.ai.knowledge.docs_index import ingest_doc
    from app.models.datasource_table import DataSourceTable

    routed: list[str] = []
    try:
        frames = SpreadsheetClient(path=file.path, file_id=str(file.id))._load_frames()
    except Exception:  # noqa: BLE001
        return routed
    if not frames:
        return routed

    for table_name, df in frames.items():
        try:
            if not smart_upload.looks_like_glossary(df, sheet_name=table_name, filename=file.filename or ""):
                continue
            body = smart_upload.glossary_to_markdown(df, sheet_name=table_name)
            if not body or not body.strip():
                continue
            title = f"{(file.filename or 'glossary')} — {table_name}"
            await ingest_doc(
                db, organization=organization, title=title, body=body,
                source="upload", data_source_id=str(data_source.id),
            )
            # Deactivate the junk queryable table (the slugged sheet name).
            try:
                tbl = (
                    await db.execute(
                        select(DataSourceTable).where(
                            DataSourceTable.datasource_id == data_source.id,
                            func.lower(DataSourceTable.name) == table_name.lower(),
                        )
                    )
                ).scalars().first()
                if tbl is not None:
                    tbl.is_active = False
                    await db.commit()
            except Exception:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            routed.append(table_name)
            logger.info("from-file: routed glossary sheet '%s' -> KnowledgeDoc (pending)", table_name)
        except Exception:  # noqa: BLE001
            logger.warning("from-file: glossary route for sheet '%s' failed", table_name, exc_info=True)
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            continue
    return routed


@router.post("/data_sources/from-file")
@requires_permission('create_data_source')
async def create_data_source_from_file(
    payload: DataSourceFromFileRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    # ── 1. Fetch the File, org-scoped (404 if not owned by the org) ──────
    file_result = await db.execute(
        select(FileModel).filter(
            FileModel.id == payload.file_id,
            FileModel.organization_id == organization.id,
        )
    )
    file = file_result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    abs_path = _resolve_upload_path(file.path or "")
    if not abs_path:
        raise HTTPException(status_code=400, detail="File content is missing or unreadable")

    # Basic extension sanity (the client also validates on read).
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Upload an Excel (.xlsx/.xls) or CSV file.",
        )

    # ── 1b. Task 5 (HYBRID_MERGE_SAME_SCHEMA): content-hash dedup + same-schema
    # append. Fail-soft — any error here falls through to today's behavior
    # (new source + new table per file).
    content_hash = ""
    try:
        from app.settings.hybrid_flags import flags as _flags
        from app.services.ingest import smart_upload

        content_hash = smart_upload.file_content_hash(abs_path)
        if _flags.MERGE_SAME_SCHEMA and content_hash:
            merged = await _try_merge_same_schema(
                db,
                organization=organization,
                current_user=current_user,
                file=file,
                abs_path=abs_path,
                content_hash=content_hash,
            )
            if merged is not None:
                return merged
    except Exception:  # noqa: BLE001 - merge is best-effort, never blocks upload
        logger.warning("from-file: merge/dedup probe failed; proceeding with new source", exc_info=True)

    # ── 2. Create the Connection (type='spreadsheet') ───────────────────
    config = {
        "file_id": str(file.id),
        "sheet_names": payload.sheet_names,
        # Resolved server-side path so the client reads without a DB lookup.
        "path": file.path,
        # Task 5: stored on the connection config (queryable JSON; least-invasive
        # spot — no new column/migration) so a byte-identical re-upload and a
        # same-schema append can find this source later. Harmless when the flag
        # is off (just metadata the client ignores).
        "content_hash": content_hash,
        # Task 5: extra same-schema files merged into this source (populated by
        # _try_merge_same_schema on a later matching upload). Empty here.
        "merged_paths": [],
    }

    # Auto-generate connection name as spreadsheet-N (mirrors create_data_source).
    count_result = await db.execute(
        select(func.count(Connection.id)).filter(
            Connection.organization_id == organization.id,
            Connection.type == "spreadsheet",
        )
    )
    existing_count = count_result.scalar() or 0
    connection = Connection(
        name=f"spreadsheet-{existing_count + 1}",
        type="spreadsheet",
        config=json.dumps(config),
        organization_id=str(organization.id),
        is_active=True,
        auth_policy="system_only",
    )
    db.add(connection)
    await db.flush()

    # ── 3. Create the DataSource + link via domain_connection ───────────
    # DataSource names are unique per organization (uq_data_sources_org_name).
    # Rather than hard-blocking a same-named upload, auto-suffix " (2)", " (3)"…
    # so the user can keep multiple snapshots of the same report. They can rename
    # later. A genuine race still surfaces the 409 below.
    base_name = (payload.data_source_name or "").strip() or (file.filename or "Spreadsheet")
    ds_name = await _dedupe_ds_name(db, str(organization.id), base_name)
    data_source = DataSource(
        name=ds_name,
        organization_id=organization.id,
        is_public=False,
        is_active=True,
        use_llm_sync=False,
        owner_user_id=current_user.id,
        description=payload.description,
    )
    data_source.connections.append(connection)
    db.add(data_source)

    try:
        await db.commit()
        await db.refresh(data_source)
    except Exception as e:
        await db.rollback()
        # Duplicate name per org is the common case (uq_data_sources_org_name).
        raise HTTPException(
            status_code=409,
            detail=(
                f"A data source named '{ds_name}' already exists in this organization. "
                "Please choose a different name."
            ),
        )

    # Creator becomes a member with manage rights (mirrors create_data_source).
    await data_source_service._create_memberships(
        db, data_source, [current_user.id], permissions=["manage"]
    )

    # ── 4. Schema discovery (fail-soft) ─────────────────────────────────
    # Reuse the SAME canonical path the demo/normal flow uses:
    #   ConnectionService.refresh_schema -> ConnectionTable
    #   DataSourceService.sync_domain_tables_from_connection -> DataSourceTable
    try:
        from app.services.connection_service import ConnectionService

        # Reload data source with its connection eagerly loaded for the sync.
        ds_q = await db.execute(
            select(DataSource)
            .options(selectinload(DataSource.connections))
            .filter(DataSource.id == data_source.id)
        )
        data_source = ds_q.scalar_one()
        conn = data_source.connections[0]

        await ConnectionService().refresh_schema(
            db=db, connection=conn, current_user=current_user
        )
        await data_source_service.sync_domain_tables_from_connection(
            db=db,
            data_source=data_source,
            connection=conn,
            max_auto_select=9999,  # activate all sheets — small files
        )
        await db.commit()
    except Exception as e:
        logger.warning(
            "from-file: schema discovery failed for data_source %s (file %s): %s",
            data_source.id, payload.file_id, e,
        )
        try:
            await db.rollback()
        except Exception:
            pass

    # ── 4b. Task 6 (HYBRID_SMART_HEADER): glossary routing ──────────────
    # If a sheet looks like a field-definition glossary, route its content into
    # the Knowledge layer (KnowledgeDoc, pending) so its terms can map onto OTHER
    # sources' columns — and deactivate the junk queryable table. Fail-soft.
    glossary_routed: list[str] = []
    try:
        from app.settings.hybrid_flags import flags as _sh_flags

        if _sh_flags.SMART_HEADER:
            glossary_routed = await _route_glossary_sheets(
                db, organization=organization, data_source=data_source, file=file, abs_path=abs_path,
            )
    except Exception:  # noqa: BLE001
        logger.warning("from-file: glossary routing failed", exc_info=True)

    # ── 5. Build the response: DataSourceSchema (+ tables[]) ─────────────
    ds_schema = await data_source_service.get_data_source(
        db, str(data_source.id), organization, current_user
    )

    try:
        tables = await data_source_service.get_data_source_schema(
            db,
            str(data_source.id),
            include_inactive=True,
            organization=organization,
            current_user=current_user,
        )
    except Exception as e:
        logger.warning("from-file: could not load tables for response: %s", e)
        tables = []

    # Return the exact DataSourceSchema shape plus the discovered tables[].
    body = json.loads(ds_schema.json()) if hasattr(ds_schema, "json") else dict(ds_schema)
    body["tables"] = [
        json.loads(t.json()) if hasattr(t, "json") else dict(t) for t in (tables or [])
    ]
    if glossary_routed:
        body["glossary_routed"] = glossary_routed
    return body
