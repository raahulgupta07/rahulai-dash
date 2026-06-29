"""Smart Dashboard Build (HYBRID_SMART_DASHBOARD) — additive sidecar.

Outputs "Generate dashboard" becomes smart: it understands the chat turn and the
agent's own data WITHOUT asking, and only asks ONE clarifying chip when there is
no usable signal. Two endpoints (both gated → {disabled:true} when flag OFF):

  GET  /api/reports/{id}/dashboard/context
       Read the last chat turn + the agent's bound data sources + whether the
       report already has charts → return a PREFILLED prompt and whether we can
       build straight away or must clarify. No questions asked of the user.

  POST /api/reports/{id}/dashboard/smart-generate   body {prompt?, size?, depth?}
       Build the dashboard. Reuses report_slides._generate_artifact (composes the
       turn's existing charts) with the user's steer prompt + size/depth folded
       in. If there are no charts AND no signal → returns needs_clarification with
       chip options instead of a 400.

Decoupled + flag-gated: flag OFF (or route absent) → the existing one-click
builder is unchanged. NEVER 500s the Outputs UX — fail-soft payloads.

NOTE: no `from __future__ import annotations` (body+permission route landmine —
stringized annotations make FastAPI mis-read the pydantic body as a query param).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_db, get_current_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.report import Report
from app.models.completion import Completion
from app.models.studio import StudioDataSource
from app.models.data_source import DataSource
from app.models.visualization import Visualization
from app.core.auth import current_user
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)

router = APIRouter(tags=["smart-dashboard"])

# Asked ONLY when there is no usable signal (cold open + empty prompt).
_CLARIFY_QUESTION = "What should this dashboard help you understand?"
_CLARIFY_OPTIONS = [
    "Track overall performance",
    "Find why a metric changed",
    "Compare segments or regions",
    "Spot risks and anomalies",
]


def _disabled():
    return {"disabled": True, "feature": "smart_dashboard"}


async def _resolve_clarify(db, organization, steer: str) -> dict:
    """Build the ONE clarify chip. Reuses the existing ambiguity gate for a
    sharper question/options when that flag is on; else falls back to the static
    pair. NEVER raises — clarify is best-effort."""
    try:
        from app.ai.clarify.ambiguity_gate import detect_ambiguity

        res = await detect_ambiguity(db, organization=organization, question=steer or "")
        if isinstance(res, dict) and res.get("ambiguous"):
            q = res.get("clarifying_question") or _CLARIFY_QUESTION
            opts = res.get("suggested_options") or _CLARIFY_OPTIONS
            return {"question": q, "options": list(opts)[:4]}
    except Exception:  # noqa: BLE001 — gate off / any error → static fallback
        logger.debug("smart-dashboard: ambiguity gate unavailable, using static clarify")
    return {"question": _CLARIFY_QUESTION, "options": _CLARIFY_OPTIONS}


def _text_of(blob) -> str:
    """Completion.prompt / .completion are JSON — pull a content string out."""
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob.strip()
    if isinstance(blob, dict):
        for k in ("content", "text", "message", "prompt"):
            v = blob.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


async def _last_turn(db: AsyncSession, report_id: str) -> dict:
    """Most recent user question + agent answer for this report. Fail-soft."""
    out = {"question": "", "answer": ""}
    try:
        rows = (await db.execute(
            select(Completion)
            .where(Completion.report_id == report_id, Completion.deleted_at.is_(None))
            .order_by(desc(Completion.turn_index), desc(Completion.created_at))
            .limit(12)
        )).scalars().all()
        for c in rows:
            role = (c.role or "").lower()
            if role == "user" and not out["question"]:
                out["question"] = _text_of(c.prompt)
            elif role == "system" and not out["answer"]:
                out["answer"] = _text_of(c.completion)
            if out["question"] and out["answer"]:
                break
    except Exception:  # noqa: BLE001
        logger.exception("smart-dashboard: last-turn read failed")
    return out


async def _agent_sources(db: AsyncSession, report: Report) -> List[dict]:
    """The agent's OWN bound data sources (no user picker). Fail-soft → []."""
    out: List[dict] = []
    try:
        if not report.studio_id:
            return out
        ds_ids = [r[0] for r in (await db.execute(
            select(StudioDataSource.agent_id).where(
                StudioDataSource.studio_id == report.studio_id,
                StudioDataSource.deleted_at.is_(None),
            )
        )).all()]
        if not ds_ids:
            return out
        rows = (await db.execute(
            select(DataSource.id, DataSource.name).where(DataSource.id.in_(ds_ids))
        )).all()
        out = [{"id": str(i), "name": n} for i, n in rows]
    except Exception:  # noqa: BLE001
        logger.exception("smart-dashboard: agent-sources read failed")
    return out


async def _has_charts(db: AsyncSession, report_id: str) -> bool:
    try:
        row = (await db.execute(
            select(Visualization.id).where(Visualization.report_id == report_id).limit(1)
        )).first()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def _prefill(turn: dict) -> str:
    """A starting prompt from the chat turn — usually the user's own question."""
    q = (turn.get("question") or "").strip()
    if q:
        return q if len(q) <= 240 else q[:240].rstrip() + "…"
    return ""


async def _load_report(db: AsyncSession, report_id: str, organization) -> Optional[Report]:
    try:
        r = (await db.execute(
            select(Report).where(
                Report.id == report_id,
                Report.organization_id == str(organization.id),
            )
        )).scalars().first()
        return r
    except Exception:  # noqa: BLE001
        logger.exception("smart-dashboard: report load failed")
        return None


@router.get("/reports/{report_id}/dashboard/context")
async def smart_dashboard_context(
    report_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Understand the turn + agent data WITHOUT asking. Returns a prefilled prompt
    and whether we can build now or must clarify."""
    if not flags.SMART_DASHBOARD:
        return _disabled()

    report = await _load_report(db, report_id, organization)
    if report is None:
        return {"ok": False, "error": "report not found"}

    turn = await _last_turn(db, report_id)
    sources = await _agent_sources(db, report)
    has_charts = await _has_charts(db, report_id)
    prefill = _prefill(turn)

    # Resolvable = we can build straight away: the turn already produced charts,
    # OR we have a prefill/question to steer from. Clarify ONLY when totally blind.
    resolvable = bool(has_charts or prefill)
    clarify = None if resolvable else await _resolve_clarify(db, organization, prefill)

    return {
        "ok": True,
        "prefill": prefill,
        "answer_preview": (turn.get("answer") or "")[:280],
        "sources": sources,           # auto — shown for trust, NOT a picker
        "has_charts": has_charts,
        "resolvable": resolvable,
        "needs_clarification": not resolvable,
        "clarify": clarify,
        "model": "auto",              # reuse the chat Auto router
    }


class SmartGenerateRequest(BaseModel):
    prompt: Optional[str] = ""        # user's steer (or the prefill, or a clarify pick)
    size: Optional[str] = ""          # compact | full
    depth: Optional[str] = ""         # exec | analyst


@router.post("/reports/{report_id}/dashboard/smart-generate")
async def smart_dashboard_generate(
    report_id: str,
    body: SmartGenerateRequest = ...,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Build the dashboard from the turn's existing charts, steered by the user's
    prompt + layout preference. If there are no charts AND no signal, return a
    clarify chip instead of an error."""
    if not flags.SMART_DASHBOARD:
        return _disabled()

    report = await _load_report(db, report_id, organization)
    if report is None:
        return {"ok": False, "error": "report not found"}

    steer = (body.prompt or "").strip()
    has_charts = await _has_charts(db, report_id)

    # No charts yet to compose AND no steer → we are blind; ask one chip.
    if not has_charts and not steer:
        turn = await _last_turn(db, report_id)
        prefill = _prefill(turn)
        if not prefill:
            return {"ok": True, "needs_clarification": True,
                    "clarify": await _resolve_clarify(db, organization, "")}
        steer = prefill   # fall back to the chat question as the steer

    # No charts but we DO have a steer → the turn never produced a dataset; tell
    # the FE to ask the agent a data question first (don't fabricate).
    if not has_charts:
        return {"ok": False, "needs_data": True,
                "message": "Ask the agent a data question first so it builds the charts, "
                           "then generate the dashboard from them."}

    # Build, reusing the proven artifact pipeline with the steer folded in.
    try:
        from app.routes.report_slides import _generate_artifact

        result = await _generate_artifact(
            mode="page", report_id=report_id, current_user=current_user,
            organization=organization, db=db,
            steer_prompt=steer, depth=(body.depth or ""), size=(body.size or ""),
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001 — surface a clean message, never a raw 500
        logger.exception("smart-dashboard generate failed")
        detail = getattr(exc, "detail", None) or str(exc)
        return {"ok": False, "error": str(detail)[:300]}
