"""Studio Auto-train API (async background job).

Makes the Studio "Auto-train" flow NON-blocking. Previously the FE ran
profiling + auto-queries + auto-evals + artifact generation sequentially and
blocked ~30-90s. Here:

  POST /studios/{studio_id}/train         (editor+) -> kicks the pipeline in the
      background via ``train_orchestrator.start_training`` and returns IMMEDIATELY
      (does NOT await the training).
  GET  /studios/{studio_id}/train/status  (viewer+) -> polls the in-process run
      status (``train_orchestrator.get_status``).

All work happens in ``app.ai.knowledge.train_orchestrator`` (own fresh session,
fail-soft per stage, never raises). Both routes are gated by ``flags.STUDIOS``
and resolve the caller's effective Studio role first. Mirrors the deps / auth /
flag + role helpers in ``app.routes.studio_artifacts`` (``tags=["studios"]``, no
``/api`` prefix — main.py mounts under /api). NEVER 500s — fail-soft JSON.

NOTE: deliberately NO ``from __future__ import annotations``.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_user
from app.dependencies import get_async_db, get_current_organization
from app.errors import AppError, ErrorCode
from app.models.organization import Organization
from app.models.user import User
from app.services.studio_access import resolve_studio_access
from app.settings.hybrid_flags import flags

from app.ai.knowledge import train_orchestrator

router = APIRouter(tags=["studios"])

# Roles that may kick off a train run.
_EDITOR_ROLES = {"owner", "editor"}


def _require_flag() -> None:
    """Short-circuit when the Studios feature is OFF (upstream-identical)."""
    if not flags.STUDIOS:
        raise AppError.not_found("studio.not_found", "Studio not found")


async def _require_role(
    db: AsyncSession, studio_id: str, user: User, *, editor: bool = False
) -> str:
    """Resolve the caller's effective role or raise 404/403.

    A 404 (not 403) is returned when the user has no access at all so the
    existence of a Studio isn't leaked to non-members.
    """
    role = await resolve_studio_access(db, studio_id, user)
    if role is None:
        raise AppError.not_found("studio.not_found", "Studio not found")
    if editor and role not in _EDITOR_ROLES:
        raise AppError.forbidden(
            ErrorCode.ACCESS_DENIED, "Editor or owner role required"
        )
    return role


@router.post("/studios/{studio_id}/train", response_model=dict)
async def start_studio_train(
    studio_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Kick the Auto-train pipeline in the background (editor+). Returns
    immediately with the run's initial status; poll the status endpoint."""
    _require_flag()
    await _require_role(db, studio_id, current_user, editor=True)

    try:
        return train_orchestrator.start_training(
            studio_id, organization.id, current_user.id
        )
    except Exception as e:  # noqa: BLE001 - never 500; report fail-soft
        return {"started": False, "status": "error", "error": str(e)}


@router.get("/studios/{studio_id}/train/status", response_model=dict)
async def get_studio_train_status(
    studio_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Poll the current/last Auto-train status for a Studio (viewer+).

    The in-process run store is per-uvicorn-worker, so a poll may land on a
    different worker than the one running the job. Fall back to the DB-persisted
    status (Studio.config['_train_status']) when the local store is idle/empty.
    """
    _require_flag()
    await _require_role(db, studio_id, current_user)

    try:
        status = train_orchestrator.get_status(studio_id)
        if isinstance(status, dict) and status.get("status") not in (None, "idle"):
            return status
        from sqlalchemy import select
        from app.models.studio import Studio

        res = await db.execute(select(Studio).where(Studio.id == studio_id))
        studio = res.scalar_one_or_none()
        cfg = getattr(studio, "config", None) if studio is not None else None
        if isinstance(cfg, dict) and isinstance(cfg.get("_train_status"), dict):
            return cfg["_train_status"]
        return status
    except Exception as e:  # noqa: BLE001 - never 500; report fail-soft
        return {"status": "error", "error": str(e)}


@router.post("/studios/{studio_id}/train/reset", response_model=dict)
async def reset_studio_train(
    studio_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Clear a stuck/failed Auto-train status (editor+).

    A run that died mid-pipeline (e.g. an LLM key failure) leaves
    ``Studio.config['_train_status']`` frozen at ``status='running'`` forever, so
    the log panel shows a perpetual spinner. This drops the persisted status (and
    the in-process store) so the next Auto-train starts clean. Fail-soft."""
    _require_flag()
    await _require_role(db, studio_id, current_user, editor=True)

    try:
        # best-effort clear the per-worker in-process store
        try:
            train_orchestrator.reset_status(studio_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - optional helper, ignore if absent
            pass

        from sqlalchemy import select
        from sqlalchemy.orm.attributes import flag_modified
        from app.models.studio import Studio

        res = await db.execute(select(Studio).where(Studio.id == studio_id))
        studio = res.scalar_one_or_none()
        if studio is not None and isinstance(getattr(studio, "config", None), dict):
            if "_train_status" in studio.config:
                studio.config.pop("_train_status", None)
                flag_modified(studio, "config")
                await db.commit()
        return {"status": "idle", "reset": True}
    except Exception as e:  # noqa: BLE001 - never 500; report fail-soft
        return {"status": "error", "error": str(e)}
