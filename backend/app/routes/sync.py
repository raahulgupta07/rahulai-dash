"""Folder Sync server endpoints (HYBRID_FOLDER_SYNC, default OFF).

The desktop Folder Sync agent watches a local folder and pushes changed
Excel/CSV files here, authenticated by an API key (``bow_`` prefix) — exactly
like Claude Code, but for data. Each file POST delta-upserts into a per-agent
DataSource:

  * a byte-identical re-push (same sha256 for the same path) is a no-op, and
  * an edited file with the SAME schema reuses / appends to the SAME data source
    (the heavy lifting lives in ``create_data_source_from_file``, which already
    does content-hash dedup + same-schema merge).

No file bytes are stored here — only the path, last-synced hash, and the ids it
resolved to live in ``folder_sync_states`` (the delta ledger).

Auth: every endpoint reuses ``mcp_auth`` (JWT OR ``X-API-Key`` / Bearer
``bow_`` key) so the headless desktop agent can authenticate with just a key.

These paths are declared WITHOUT the ``/api`` prefix — main.py adds ``/api`` at
include time (mirrors data_source_from_file). So ``/sync/file`` becomes
``/api/sync/file``.
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_db
from app.models.folder_sync import FolderSyncState
from app.models.organization import Organization
from app.models.studio import Studio, StudioDataSource
from app.models.user import User
from app.routes.mcp import mcp_auth
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


def _require_flag() -> None:
    """Gate every Folder Sync endpoint behind HYBRID_FOLDER_SYNC."""
    if not flags.FOLDER_SYNC:
        raise HTTPException(status_code=404, detail="Folder Sync is not enabled")


def _stem(filename: Optional[str]) -> str:
    """Derive a human data-source name from a filename (drop the extension)."""
    name = (filename or "").strip()
    if not name:
        return "Folder Sync File"
    # Strip the last extension only (foo.bar.xlsx -> foo.bar).
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name or "Folder Sync File"


async def _ensure_studio_link(
    db: AsyncSession,
    *,
    org_id: str,
    studio_id: str,
    data_source_id: str,
) -> Optional[str]:
    """Ensure a StudioDataSource row links studio_id <-> data_source_id.

    Org-scoped: the Studio must exist, not be soft-deleted, and belong to the
    org. Fail-soft — returns the studio_id on success (or if the link already
    exists), and None if the studio is missing / not owned. Never raises into
    the caller (the file sync must not crash on a bad binding).
    """
    try:
        studio = (
            await db.execute(
                select(Studio).where(
                    Studio.id == studio_id,
                    Studio.organization_id == org_id,
                    Studio.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if studio is None:
            logger.warning(
                "sync: target_studio_id %s not found / not owned by org %s — skipping bind",
                studio_id, org_id,
            )
            return None

        existing = (
            await db.execute(
                select(StudioDataSource).where(
                    StudioDataSource.studio_id == studio_id,
                    StudioDataSource.agent_id == data_source_id,
                    StudioDataSource.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            # StudioDataSource has only studio_id + agent_id (no org column);
            # it's already org-scoped via the Studio we verified above.
            db.add(StudioDataSource(studio_id=studio_id, agent_id=data_source_id))
            await db.flush()
        return studio_id
    except Exception:  # noqa: BLE001 — binding is best-effort, never blocks sync
        logger.warning("sync: studio bind failed for studio %s", studio_id, exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


@router.post("/sync/file")
async def sync_file(
    request: Request,
    file: UploadFile = File(...),
    source_path: str = Form(...),
    sha256: str = Form(...),
    machine_label: str = Form(None),
    target_studio_id: str = Form(None),
    auth: Tuple[User, Organization] = Depends(mcp_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """Hot path: the desktop agent pushes a changed file's bytes + its sha256.

    Delta-upsert by (organization_id, source_path):
      * unchanged hash  -> skipped (no ingest)
      * new path        -> ingest + create/reuse data source, status='new'
      * changed hash    -> re-ingest (reuses same source if same schema),
                           status='updated'
    """
    _require_flag()
    user, organization = auth
    # Capture scalar ids + name up-front. ``create_data_source_from_file`` commits
    # internally, which expires every ORM object in this session — touching
    # ``user.id`` / ``organization.id`` afterwards would trigger a lazy reload that
    # fails under async (greenlet_spawn). Plain strings sidestep that entirely.
    org_id = str(organization.id)
    user_id = str(user.id)
    file_name = file.filename

    # ── Look up the existing ledger row for this (org, path) ─────────────
    row = (
        await db.execute(
            select(FolderSyncState).where(
                FolderSyncState.organization_id == org_id,
                FolderSyncState.source_path == source_path,
                FolderSyncState.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    # ── No-op fast path: byte-identical re-push of a known path ──────────
    if row is not None and row.file_hash == sha256:
        ds_id, st_id = row.data_source_id, row.studio_id
        row.status = "skipped"
        row.last_sync_at = datetime.utcnow()
        if machine_label:
            row.machine_label = machine_label
        await db.commit()
        return {"status": "skipped", "data_source_id": ds_id, "studio_id": st_id}

    new_status = "new" if row is None else "updated"

    # ── Ingest + (re)build the data source — wrapped so failures persist
    # an 'error' on the ledger row instead of vanishing. ─────────────────
    try:
        # 1. Persist the uploaded bytes as a File row.
        from app.services.file_service import FileService

        file_schema = await FileService().upload_file(
            db=db,
            file=file,
            current_user=user,
            organization=organization,
        )
        file_id = str(file_schema.id)

        # 2. Turn the File into / merge into a Data Agent (DataSource). This
        # helper already does content-hash dedup + same-schema append, so an
        # edited file with the same schema feeds the SAME source. NOTE: it
        # commits internally → ``user``/``organization``/``row`` are now expired.
        from app.routes.data_source_from_file import (
            DataSourceFromFileRequest,
            create_data_source_from_file,
        )

        payload = DataSourceFromFileRequest(
            file_id=file_id,
            data_source_name=_stem(file_name),
        )
        result = await create_data_source_from_file(
            payload,
            current_user=user,
            db=db,
            organization=organization,
        )
        data_source_id = (result or {}).get("id")
        data_source_id = str(data_source_id) if data_source_id else None

        # 3. Optional Studio (agent) binding — fail-soft.
        resolved_studio_id = None
        if target_studio_id and data_source_id:
            resolved_studio_id = await _ensure_studio_link(
                db,
                org_id=org_id,
                studio_id=target_studio_id,
                data_source_id=data_source_id,
            )

        # 4. Upsert the ledger row. Re-query fresh — the pre-ingest ``row`` was
        # expired by the inner commit; never touch it again.
        row = (
            await db.execute(
                select(FolderSyncState).where(
                    FolderSyncState.organization_id == org_id,
                    FolderSyncState.source_path == source_path,
                    FolderSyncState.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = FolderSyncState(organization_id=org_id, source_path=source_path)
            db.add(row)
        row.user_id = user_id
        row.machine_label = machine_label
        row.file_name = file_name
        row.file_hash = sha256
        row.file_id = file_id
        row.data_source_id = data_source_id
        row.studio_id = resolved_studio_id
        row.status = new_status
        row.error = None
        row.last_sync_at = datetime.utcnow()
        await db.commit()

        return {
            "status": new_status,
            "data_source_id": data_source_id,
            "studio_id": resolved_studio_id,
        }

    except HTTPException:
        await _persist_error(db, org_id, source_path, machine_label,
                             file_name, user_id, "ingest failed")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync: file sync failed for path %s", source_path)
        await _persist_error(db, org_id, source_path, machine_label,
                             file_name, user_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Folder Sync failed: {exc}")


async def _persist_error(
    db: AsyncSession,
    org_id: str,
    source_path: str,
    machine_label: Optional[str],
    file_name: Optional[str],
    user_id: str,
    error: str,
) -> None:
    """Best-effort: stamp status='error' + the error text on the ledger row.

    Runs after a failed ingest in its own try-block; never raises (the caller
    is already surfacing the original error). Takes plain string ids — the ORM
    user/org objects are expired by this point.
    """
    try:
        await db.rollback()
    except Exception:  # noqa: BLE001
        pass
    try:
        row = (
            await db.execute(
                select(FolderSyncState).where(
                    FolderSyncState.organization_id == org_id,
                    FolderSyncState.source_path == source_path,
                    FolderSyncState.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = FolderSyncState(
                organization_id=org_id,
                source_path=source_path,
            )
            db.add(row)
        row.user_id = user_id
        if machine_label:
            row.machine_label = machine_label
        if file_name:
            row.file_name = file_name
        row.status = "error"
        row.error = (error or "")[:4000]
        row.last_sync_at = datetime.utcnow()
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("sync: could not persist error state for %s", source_path, exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


@router.get("/sync/status")
async def sync_status(
    auth: Tuple[User, Organization] = Depends(mcp_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """Return the org's sync ledger, grouped by machine, shaped for the UI."""
    _require_flag()
    _, organization = auth

    rows = (
        await db.execute(
            select(FolderSyncState)
            .where(
                FolderSyncState.organization_id == str(organization.id),
                FolderSyncState.deleted_at.is_(None),
            )
            .order_by(FolderSyncState.last_sync_at.desc().nullslast())
        )
    ).scalars().all()

    machines: dict[str, dict] = {}
    for r in rows:
        label = r.machine_label or "Unknown machine"
        m = machines.get(label)
        if m is None:
            m = {"machine_label": label, "files": 0, "last_sync_at": None, "paths": []}
            machines[label] = m
        m["files"] += 1
        last = r.last_sync_at.isoformat() if r.last_sync_at else None
        # Track the newest sync time for the machine header.
        if last and (m["last_sync_at"] is None or last > m["last_sync_at"]):
            m["last_sync_at"] = last
        m["paths"].append({
            "source_path": r.source_path,
            "file_name": r.file_name,
            "status": r.status,
            "data_source_id": r.data_source_id,
            "studio_id": r.studio_id,
            "last_sync_at": last,
        })

    return {"machines": list(machines.values())}


@router.get("/sync/agents")
async def sync_agents(
    auth: Tuple[User, Organization] = Depends(mcp_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """List the org's Studios for the desktop agent's "sync into agent" dropdown."""
    _require_flag()
    _, organization = auth

    rows = (
        await db.execute(
            select(Studio)
            .where(
                Studio.organization_id == str(organization.id),
                Studio.deleted_at.is_(None),
            )
            .order_by(Studio.name)
        )
    ).scalars().all()

    return [{"id": str(s.id), "name": s.name} for s in rows]


class SyncKeyRequest(BaseModel):
    name: str = "Folder Sync"


@router.post("/sync/key")
async def sync_key(
    request: Request,
    body: SyncKeyRequest,
    auth: Tuple[User, Organization] = Depends(mcp_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """Mint an API key for the desktop Folder Sync agent (plaintext shown once)."""
    _require_flag()
    user, organization = auth

    from app.services.api_key_service import ApiKeyService
    from app.schemas.api_key_schema import ApiKeyCreate

    created = await ApiKeyService().create_api_key(
        db=db,
        data=ApiKeyCreate(name=body.name or "Folder Sync"),
        user=user,
        organization=organization,
    )

    return {
        "key": created.key,
        "prefix": created.key_prefix,
        "server_url": str(request.base_url).rstrip("/"),
    }
