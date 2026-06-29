"""Smart Upload API — classify uploaded files, then apply confirmed routes.

Exposes the Smart Upload brain (``app.services.smart_upload.classifier`` +
``contract``) over HTTP and APPLIES confirmed routes by calling the existing
knowledge-subsystem sinks (``app.services.smart_upload.apply``).

Flow (the client uploads via ``POST /api/files`` FIRST, then references the
returned file ids here):
  1. POST /api/studios/{studio_id}/smart-upload/classify  -> proposed routes.
  2. (UI lets the user confirm/override the per-file destinations.)
  3. POST /api/studios/{studio_id}/smart-upload/apply      -> writes via sinks.

Gating mirrors ``studio_autoconfigure.py``: every route is behind
``flags.SMART_UPLOAD`` (env ``HYBRID_SMART_UPLOAD``) and 404s when OFF, exactly
like the Studios gate. Authorization = org scope + studio role: viewer+ may
classify (read-only), editor/owner may apply (writes). Answer-changing writes
land as pending via the sinks — this layer never force-approves.

Mounted under /api by main.py. NOTE: no ``from __future__ import annotations``
(body pydantic models on routes can be mis-read as query params under stringized
annotations — the data_source_from_file landmine).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_user
from app.dependencies import get_async_db, get_current_organization
from app.models.file import File as FileModel
from app.models.organization import Organization
from app.models.user import User
from app.services.smart_upload import apply as smart_apply
from app.services.smart_upload import classifier
from app.services.studio_access import resolve_studio_access
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)

router = APIRouter(tags=["studios"])

_EDITOR_ROLES = {"owner", "editor"}


# --------------------------------------------------------------------------- #
# Gate + role helpers (mirror studio_autoconfigure.py)
# --------------------------------------------------------------------------- #
def _require_flag() -> None:
    """404 when SMART_UPLOAD is OFF — never leak the route's existence."""
    if not getattr(flags, "SMART_UPLOAD", False):
        raise HTTPException(status_code=404, detail="Not found")


async def _require_role(
    db: AsyncSession, studio_id: str, user: User, *, editor: bool = False
) -> str:
    """Resolve the caller's effective studio role or raise 404/403.

    404 (not 403) when the user has no access at all so a Studio's existence
    isn't leaked to non-members; 403 when a viewer attempts an editor action.
    """
    role = await resolve_studio_access(db, studio_id, user)
    if role is None:
        raise HTTPException(status_code=404, detail="Studio not found")
    if editor and role not in _EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="Editor or owner role required")
    return role


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class ClassifyRequest(BaseModel):
    file_ids: List[str]
    data_source_id: Optional[str] = None


class ApplyItem(BaseModel):
    file_id: Optional[str] = None
    dest: str
    filename: Optional[str] = None

    class Config:
        extra = "allow"  # carry through reason/confidence/signals harmlessly


class ApplyRequest(BaseModel):
    items: List[ApplyItem]
    data_source_id: Optional[str] = None
    train: bool = False


# --------------------------------------------------------------------------- #
# CLASSIFY (viewer+) — no writes
# --------------------------------------------------------------------------- #
@router.post("/studios/{studio_id}/smart-upload/classify")
async def smart_upload_classify(
    studio_id: str,
    body: ClassifyRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> Dict[str, Any]:
    """Classify already-uploaded files into routes. WRITES NOTHING.

    Loads each File (org-scoped), resolves its on-disk path, runs the heuristic
    classifier (+ a fail-soft small-LLM tie-break for the uncertain ones) and
    returns one route record per file plus an auto/needs-confirm summary.
    """
    _require_flag()
    await _require_role(db, studio_id, current_user)

    # Resolve each file to {path, filename}, preserving order + ids.
    files: List[Dict[str, str]] = []
    file_ids: List[str] = []
    for fid in (body.file_ids or []):
        res = await db.execute(
            select(FileModel).where(
                FileModel.id == str(fid),
                FileModel.organization_id == organization.id,
            )
        )
        f = res.scalar_one_or_none()
        if f is None:
            # Keep a placeholder so the record count matches the request.
            files.append({"path": "", "filename": ""})
            file_ids.append(str(fid))
            continue
        path = smart_apply._resolve_path(f.path or "") or ""
        files.append({"path": path, "filename": f.filename or ""})
        file_ids.append(str(f.id))

    # Resolve a small LLM for the tie-break — fail-soft (heuristic-only on None).
    llm = None
    try:
        from app.services.llm_service import LLMService
        llm = await LLMService().get_default_model(
            db, organization, current_user, is_small=True
        )
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.classify: small-model resolve failed",
                       exc_info=True)
        llm = None

    records = await classifier.classify_batch(files, llm=llm,
                                              organization=organization)

    items: List[Dict[str, Any]] = []
    auto = 0
    needs_confirm = 0
    for fid, rec in zip(file_ids, records):
        rec = dict(rec)
        rec["file_id"] = fid
        items.append(rec)
        if rec.get("needs_confirm"):
            needs_confirm += 1
        else:
            auto += 1

    return {
        "items": items,
        "summary": {"auto": auto, "needs_confirm": needs_confirm,
                    "total": len(items)},
    }


# --------------------------------------------------------------------------- #
# APPLY (editor+) — writes via existing sinks (answer-changing => pending)
# --------------------------------------------------------------------------- #
@router.post("/studios/{studio_id}/smart-upload/apply")
async def smart_upload_apply(
    studio_id: str,
    body: ApplyRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> Dict[str, Any]:
    """Apply confirmed route records by dispatching each to its existing sink.

    Each item is applied in its own try/except (one failure never blocks the
    rest). If ``train`` is true, a background studio train run is kicked
    afterwards (fail-soft). Returns ``{applied, results:[...]}``.
    """
    _require_flag()
    await _require_role(db, studio_id, current_user, editor=True)

    items = [it.dict() for it in (body.items or [])]
    summary = await smart_apply.apply_routes(
        db,
        organization=organization,
        current_user=current_user,
        studio_id=studio_id,
        data_source_id=body.data_source_id,
        items=items,
    )

    if body.train:
        try:
            from app.ai.knowledge import train_orchestrator
            train_orchestrator.start_training(
                str(studio_id), str(organization.id), str(current_user.id)
            )
            summary["train_started"] = True
        except Exception:  # noqa: BLE001
            logger.warning("smart_upload.apply: start_training failed",
                           exc_info=True)
            summary["train_started"] = False

    return summary
