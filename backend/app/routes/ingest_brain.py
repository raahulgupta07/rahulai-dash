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
import logging
import os
import tempfile
import time
from typing import List, Optional

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


def _disabled():
    return {"disabled": True, "feature": "ingest_brain"}


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

    started = time.monotonic()
    suffix = os.path.splitext(file.filename or "")[1] or ".bin"
    tmp_path = ""
    # Fetch the org's already-known columns so UNIFY can propose cross-source
    # joins (fail-soft: any error → no existing columns → no joins, never 500).
    existing_columns = []
    try:
        rows = (await db.execute(
            select(ColumnProfileModel).where(
                ColumnProfileModel.organization_id == str(organization.id),
                ColumnProfileModel.deleted_at.is_(None),
            ).limit(2000)
        )).scalars().all()
        for r in rows:
            existing_columns.append({
                "ref": f"{r.table_name or 'table'}.{r.column_name}",
                "normalized_name": r.normalized_name or "",
                "semantic_role": r.semantic_role or "category",
                "sample_values": r.sample_values or [],
            })
    except Exception:  # noqa: BLE001
        logger.exception("ingest-brain: existing-columns fetch failed (continuing without joins)")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        result = await run_pipeline(tmp_path, file.filename or "upload",
                                    organization=organization, db=db,
                                    existing_columns=existing_columns)
    except Exception as exc:  # noqa: BLE001 — fail-soft, never 500 the upload UX
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
