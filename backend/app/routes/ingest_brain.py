"""Universal Ingest Brain routes (ROADMAP F09, Phase 1) — additive sidecar.

Two endpoints, both gated by ``flags.INGEST_BRAIN`` (return 200 {disabled:true}
when OFF so the UI hides cleanly):

  POST /api/ingest-brain/preview            (multipart: file)
       Run the pipeline on an uploaded file and return the PREVIEW (tables read,
       header rows, merged-cell/blank-row notes, per-column profile, join hints)
       WITHOUT committing anything. This is the non-negotiable "show before you
       reshape" safety gate. Pure read — touches no DataSource, no agent path.

  POST /api/ingest-brain/profiles/{data_source_id}   (json: {profiles:[...]})
       Persist confirmed ColumnProfiles (status='pending') for an existing
       DataSource so the agent/user can see each column's meaning/role/unit.
       Review-gated; never auto-trusted.

Deliberately decoupled from the critical ``create_data_source_from_file`` path:
the normal upload still creates the queryable DataSource; this only ADDS deep
understanding on top. So with the flag off — or this route absent — ingest is
byte-identical to today.

NOTE: no ``from __future__ import annotations`` (body+permission route landmine —
stringized annotations make FastAPI mis-read the pydantic body as a query param).
"""
import asyncio
import logging
import os
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_db, get_current_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.column_profile import ColumnProfile as ColumnProfileModel
from app.core.auth import current_user
from app.settings.hybrid_flags import flags
from app.services.ingest_brain.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest-brain"])

_MAX_PREVIEW_ROWS = 8   # rows echoed per table in the preview (just a sample)

# In-process job store for async parse (Phase C worker offload). Bounded; oldest
# jobs evicted. Fine for one app process; a multi-worker bake would move this to
# Redis (noted). job = {status, result, error, created}.
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_MAX = 200


def _disabled():
    return {"disabled": True, "feature": "ingest_brain"}


async def _existing_columns(db: AsyncSession, organization) -> List[Dict[str, Any]]:
    """The org's already-known columns (for UNIFY cross-source joins). Fail-soft."""
    out: List[Dict[str, Any]] = []
    try:
        rows = (await db.execute(
            select(ColumnProfileModel).where(
                ColumnProfileModel.organization_id == str(organization.id),
                ColumnProfileModel.deleted_at.is_(None),
            ).limit(2000)
        )).scalars().all()
        for r in rows:
            out.append({
                "ref": f"{r.table_name or 'table'}.{r.column_name}",
                "normalized_name": r.normalized_name or "",
                "semantic_role": r.semantic_role or "category",
                "sample_values": r.sample_values or [],
            })
    except Exception:  # noqa: BLE001
        logger.exception("ingest-brain: existing-columns fetch failed (continuing without joins)")
    return out


async def _run_preview(db: AsyncSession, organization, filename: str,
                       file_bytes: bytes) -> Dict[str, Any]:
    """Shared preview core: build vision callable, run pipeline on bytes, serialize.

    Used by both the sync /preview and the async job. NEVER raises — returns an
    error payload instead.
    """
    started = time.monotonic()
    existing_columns = await _existing_columns(db, organization)

    # Phase B: wire the org's OpenRouter vision model (scanned/image + charts).
    vision_infer = None
    try:
        from app.services.ingest_brain.vision_client import build_vision_infer
        vision_infer = await build_vision_infer(db, organization)
    except Exception:  # noqa: BLE001
        logger.exception("ingest-brain: vision client build failed (continuing without vision)")

    suffix = os.path.splitext(filename or "")[1] or ".bin"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        result = await run_pipeline(tmp_path, filename or "upload",
                                    organization=organization, db=db,
                                    existing_columns=existing_columns,
                                    vision_infer=vision_infer)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest-brain preview failed")
        return {"ok": False, "error": str(exc)[:300], "tables": [], "profiles": []}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    tables = [{
        "name": t.name, "sheet": t.sheet, "region_bbox": t.region_bbox,
        "header": t.header, "row_count": len(t.rows),
        "sample_rows": [[("" if v is None else v) for v in r] for r in t.rows[:_MAX_PREVIEW_ROWS]],
        "notes": t.notes,
    } for t in result.tables]

    return {
        "ok": result.ok,
        "error": result.error,
        "source": {"filename": result.source.filename, "kind": result.source.kind,
                   "ext": result.source.ext} if result.source else None,
        "tables": tables,
        "profiles": [_profile_dict(p) for p in result.profiles],
        "prose": [{"title": pb.title, "body": pb.body[:1500], "page": pb.page}
                  for pb in result.prose[:20]],
        "join_candidates": [{"left": j.left_ref, "right": j.right_ref,
                             "confidence": j.confidence, "reason": j.reason}
                            for j in result.join_candidates],
        "preview": {
            "summary": result.preview.summary,
            "table_notes": result.preview.table_notes,
            "join_notes": result.preview.join_notes,
            "auto_confirmable": result.preview.auto_confirmable,
        },
        "ms": int((time.monotonic() - started) * 1000),
    }


def _profile_dict(p) -> dict:
    return {
        "name": p.name, "normalized_name": p.normalized_name, "dtype": p.dtype,
        "unit": p.unit, "null_pct": p.null_pct, "cardinality": p.cardinality,
        "sample_values": p.sample_values, "pii_flag": p.pii_flag,
        "semantic_role": p.semantic_role, "synonyms": p.synonyms,
        "meaning": p.meaning, "maps_to": p.maps_to, "source_ref": p.source_ref,
    }


@router.post("/ingest-brain/preview")
async def ingest_brain_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    if not flags.INGEST_BRAIN:
        return _disabled()
    file_bytes = await file.read()
    return await _run_preview(db, organization, file.filename or "upload", file_bytes)


def _evict_jobs():
    if len(_JOBS) <= _JOBS_MAX:
        return
    for k in sorted(_JOBS, key=lambda j: _JOBS[j].get("created", 0))[: len(_JOBS) - _JOBS_MAX]:
        _JOBS.pop(k, None)


async def _job_worker(job_id: str, org_id: str, filename: str, file_bytes: bytes):
    # Own session — the request session is closed by the time this runs.
    created = _JOBS.get(job_id, {}).get("created", time.time())
    try:
        from app.dependencies import async_session_maker
        from app.models.organization import Organization as OrgModel
        async with async_session_maker() as db:
            org = (await db.execute(
                select(OrgModel).where(OrgModel.id == org_id))).scalars().first()
            if org is None:
                _JOBS[job_id] = {"status": "error", "error": "organization not found", "created": created}
                return
            res = await _run_preview(db, org, filename, file_bytes)
        _JOBS[job_id] = {"status": "done", "result": res, "created": created}
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest-brain job %s failed", job_id)
        _JOBS[job_id] = {"status": "error", "error": str(exc)[:300], "created": created}


@router.post("/ingest-brain/preview-async")
async def ingest_brain_preview_async(
    file: UploadFile = File(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Phase C: heavy files (scanned/vision/large PDF) parse in the background so
    the upload returns instantly. Poll /ingest-brain/job/{id}."""
    if not flags.INGEST_BRAIN:
        return _disabled()
    file_bytes = await file.read()
    org_id = str(organization.id)
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "created": time.time()}
    _evict_jobs()
    # strong ref so the task isn't GC'd; fire-and-forget (own session inside)
    task = asyncio.create_task(
        _job_worker(job_id, org_id, file.filename or "upload", file_bytes))
    _JOBS[job_id]["_task"] = task
    return {"job_id": job_id, "status": "running"}


@router.get("/ingest-brain/job/{job_id}")
async def ingest_brain_job(
    job_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
):
    if not flags.INGEST_BRAIN:
        return _disabled()
    job = _JOBS.get(job_id)
    if not job:
        return {"status": "unknown"}
    if job["status"] == "done":
        return {"status": "done", "result": job["result"]}
    if job["status"] == "error":
        return {"status": "error", "error": job.get("error", "")}
    return {"status": "running"}


class ProfileIn(BaseModel):
    name: str
    normalized_name: Optional[str] = ""
    dtype: Optional[str] = "text"
    unit: Optional[str] = ""
    null_pct: Optional[float] = 0.0
    cardinality: Optional[int] = 0
    sample_values: Optional[List[str]] = None
    pii_flag: Optional[bool] = False
    semantic_role: Optional[str] = "category"
    synonyms: Optional[List[str]] = None
    meaning: Optional[str] = ""
    maps_to: Optional[str] = ""
    source_ref: Optional[dict] = None
    table_name: Optional[str] = ""


class CommitProfilesRequest(BaseModel):
    profiles: List[ProfileIn]


@router.post("/ingest-brain/profiles/{data_source_id}")
async def commit_profiles(
    data_source_id: str,
    body: CommitProfilesRequest = ...,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    if not flags.INGEST_BRAIN:
        return _disabled()

    org_id = str(organization.id)
    written = 0
    try:
        for p in body.profiles:
            row = ColumnProfileModel(
                organization_id=org_id,
                data_source_id=data_source_id,
                table_name=p.table_name or (p.source_ref or {}).get("sheet"),
                column_name=p.name,
                normalized_name=p.normalized_name,
                dtype=p.dtype, unit=p.unit, null_pct=p.null_pct or 0.0,
                cardinality=p.cardinality or 0, sample_values=p.sample_values,
                pii_flag=bool(p.pii_flag), semantic_role=p.semantic_role,
                synonyms=p.synonyms, meaning=p.meaning, maps_to=p.maps_to,
                source_ref=p.source_ref, status="pending",
            )
            db.add(row)
            written += 1
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest-brain commit_profiles failed")
        await db.rollback()
        return {"ok": False, "error": str(exc)[:300], "written": 0}

    return {"ok": True, "written": written, "status": "pending",
            "note": "Profiles saved as pending — approve in Knowledge → Review."}
