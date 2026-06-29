"""One-click dashboard / slide-deck generation for a report (HYBRID_ONECLICK_ARTIFACTS).

Builds a REAL artifact (mode='page' dashboard OR mode='slides' deck) from a
report's EXISTING visualizations, outside the chat planner. Reuses the exact chat
pipeline (`CreateArtifactTool`: page → React dashboard; slides → LLM python-pptx →
PptxCodeExecutor → PptxPreviewService → preview PNGs + pptx_path), so the produced
artifact is identical to one the agent would make in chat — and `ArtifactFrame`
(mode-filter='page'|'slides') renders it with real charts instead of a dead
"No artifacts yet" / client-side `SlidesPanel` placeholder.

Two bare paths (both gated, mounted `/api`):
  POST /api/reports/{id}/dashboard/generate  → mode='page'
  POST /api/reports/{id}/slides/generate     → mode='slides'

Gated on ``flags.ONECLICK_ARTIFACTS`` (HYBRID_ONECLICK_ARTIFACTS, default OFF) →
404 when off so a fresh deploy behaves exactly like upstream.

The tool is invoked with a minimal, hand-built ``runtime_ctx`` (db/report/user/
organization/model). The page/slides branches do not need the planner's
context_hub/context_view/head_completion — those reads are all guarded in the
tool and degrade to empty when absent. The model is the org's default LLM (same
one the planner uses). NOTE page mode runs a Playwright preview screenshot only
when the model supports vision; otherwise it just saves the artifact + a
background thumbnail.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_user
from app.dependencies import get_async_db, get_current_organization
from app.models.organization import Organization
from app.models.report import Report
from app.models.user import User
from app.models.visualization import Visualization
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)

router = APIRouter(tags=["report-slides"])


def _ensure_enabled() -> None:
    """404 (feature locked) unless HYBRID_ONECLICK_ARTIFACTS is on — mirrors
    routes/me_groups.py so the route's existence isn't leaked when off."""
    if not flags.ONECLICK_ARTIFACTS:
        raise HTTPException(status_code=404, detail="Not found")


# Per-mode codegen prompt + human label for error/result messages.
_MODE_PROMPTS = {
    "slides": (
        "Create a clean, professional slide deck from the report's existing "
        "charts: a title slide, then one slide per chart with a native pptx "
        "chart and a short takeaway, plus a closing summary slide."
    ),
    "page": (
        "Build a polished interactive dashboard from the report's existing "
        "charts: KPI cards for the headline numbers up top, then the charts in a "
        "responsive grid, each with a short title. One cohesive page."
    ),
}
_MODE_LABEL = {"slides": "Slide", "page": "Dashboard"}


async def _load_report(db: AsyncSession, report_id: str, organization) -> Report:
    """Load a report org-scoped (404 if missing / not in this org)."""
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.organization_id == organization.id,
            Report.deleted_at.is_(None),
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


async def _generate_artifact(
    *, mode: str, report_id: str, current_user, organization, db: AsyncSession,
    steer_prompt: str = "", depth: str = "", size: str = "",
) -> dict:
    """Shared builder for both modes. Runs the chat create_artifact pipeline over
    the report's existing visualizations and returns the result dict. Deletes its
    own artifact on hard failure so a failed attempt leaves no stale empty
    artifact (which would flip hasPageArtifact / hasSlidesArtifact on the FE).

    ``steer_prompt`` / ``depth`` / ``size`` (Smart Dashboard, all optional) fold a
    user's intent + layout preference into the build prompt. Empty = today's
    behavior byte-for-byte."""
    label = _MODE_LABEL.get(mode, "Artifact")
    report = await _load_report(db, report_id, organization)

    # All visualizations for this report — the tool filters to success-status.
    viz_rows = (
        await db.execute(
            select(Visualization.id).where(Visualization.report_id == report.id)
        )
    ).all()
    viz_ids = [str(r[0]) for r in viz_rows]
    if not viz_ids:
        raise HTTPException(
            status_code=400,
            detail="This report has no charts yet — ask the agent to create some first.",
        )

    # Org default LLM (same model the planner uses). Codegen needs it.
    model = await organization.get_default_llm_model(db)
    if model is None:
        raise HTTPException(
            status_code=400,
            detail="No default LLM model configured. Set one in Settings > LLM.",
        )

    # Minimal runtime_ctx — context_hub/context_view/head_completion are
    # intentionally None; all reads of them in the tool are guarded and degrade
    # to empty (no conversation/instruction context needed to build from existing
    # charts).
    runtime_ctx = {
        "db": db,
        "organization": organization,
        "user": current_user,
        "settings": None,            # → allow_llm_see_data defaults True (guarded)
        "report": report,
        "head_completion": None,
        "model": model,
        "sigkill_event": None,
        "context_hub": None,
        "context_view": None,
        "instruction_context_builder": None,
    }

    default_title = "Presentation" if mode == "slides" else (report.title or "Dashboard")
    base_prompt = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["page"])
    # Smart Dashboard: fold the user's steer + layout preference into the prompt.
    steer_bits = []
    if (steer_prompt or "").strip():
        steer_bits.append(f"USER FOCUS — build the dashboard to answer: {steer_prompt.strip()}")
    if depth == "exec":
        steer_bits.append("AUDIENCE: executive — lead with the headline KPIs, one key chart, and the decision; keep it tight.")
    elif depth == "analyst":
        steer_bits.append("AUDIENCE: analyst — include the full breakdown: trends, segment splits, and a drill-down table.")
    if size == "compact":
        steer_bits.append("SIZE: compact — at most 4–5 widgets, the most important ones only.")
    elif size == "full":
        steer_bits.append("SIZE: full — a complete multi-section dashboard.")
    full_prompt = base_prompt if not steer_bits else (base_prompt + "\n\n" + "\n".join(steer_bits))
    tool_input = {
        "mode": mode,
        "visualization_ids": viz_ids,
        "title": (report.title or default_title).strip() or default_title,
        "prompt": full_prompt,
    }

    # Sense-Making: fold the persisted decision card into the prompt (SAFE
    # prompt-injection path only — no artifact-iframe plumbing). Fail-soft:
    # sm None → behaves exactly as today.
    if flags.SENSE_MAKING:
        try:
            from app.ai.knowledge.sense_maker import get_stored_sense_making

            sm = await get_stored_sense_making(db, str(report.id))
            if sm:
                tool_input["sense_making"] = sm
        except Exception:  # noqa: BLE001 — never break artifact generation
            logger.warning("sense_making fetch failed for report %s", report_id, exc_info=True)

    from app.ai.tools.implementations.create_artifact import CreateArtifactTool

    tool = CreateArtifactTool()
    artifact_id: Optional[str] = None
    slide_count = 0
    error: Optional[str] = None

    try:
        async for evt in tool.run_stream(tool_input, runtime_ctx):
            payload = getattr(evt, "payload", None) or {}
            if payload.get("artifact_id") and not artifact_id:
                artifact_id = str(payload["artifact_id"])
            out = payload.get("output")
            obs = payload.get("observation")
            if isinstance(out, dict):
                if out.get("artifact_id"):
                    artifact_id = str(out["artifact_id"])
                if out.get("error"):
                    error = str(out["error"])
            if isinstance(obs, dict):
                slide_count = int(obs.get("slide_count") or slide_count)
    except Exception as e:  # noqa: BLE001 — never leak a raw 500 trace
        logger.exception("%s generation failed for report %s", label, report_id)
        raise HTTPException(status_code=502, detail=f"{label} generation failed: {e}")

    if not artifact_id:
        raise HTTPException(status_code=502, detail=error or f"{label} generation produced no artifact.")

    # Re-query: a built-but-failed artifact (e.g. pptx execution error, or a page
    # render error) is marked status='failed' WITHOUT output.success False, so it
    # must be detected here — else the FE flips to an empty ArtifactFrame. Drop it
    # so the "Generate" button stays visible for a retry.
    from app.models.artifact import Artifact

    artifact = await db.get(Artifact, artifact_id)
    if artifact is not None and (artifact.status or "") == "failed":
        detail = f"{label} generation failed."
        rerr = getattr(artifact, "render_errors", None)
        if rerr:
            detail = f"{label} generation failed: {rerr[0]}"
        try:
            await db.delete(artifact)
            await db.commit()
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            await db.rollback()
        raise HTTPException(status_code=502, detail=detail)

    return {
        "artifact_id": artifact_id,
        "slide_count": slide_count,
        "mode": mode,
        "error": error,
    }


@router.post("/reports/{report_id}/slides/generate")
async def generate_report_slides(
    report_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Build a real slides artifact (mode='slides') from this report's charts."""
    _ensure_enabled()
    return await _generate_artifact(
        mode="slides", report_id=report_id,
        current_user=current_user, organization=organization, db=db,
    )


@router.post("/reports/{report_id}/dashboard/generate")
async def generate_report_dashboard(
    report_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Build a real dashboard artifact (mode='page') from this report's charts."""
    _ensure_enabled()
    return await _generate_artifact(
        mode="page", report_id=report_id,
        current_user=current_user, organization=organization, db=db,
    )


# --------------------------------------------------------------------------- #
# Excel workbook — read-only, NO LLM. One sheet per query's latest success step.
# The /api/queries list endpoint strips step row data, so the FE can't build a
# workbook client-side from existing charts; this returns the real grids from
# steps.data (parquet-hydrated) so the Excel tab auto-fills.
# --------------------------------------------------------------------------- #

_WORKBOOK_MAX_ROWS = 5000     # per sheet, email/UI-safe
_WORKBOOK_MAX_SHEETS = 50


def _coerce_grid(data) -> Optional[dict]:
    """Coerce a step's ``data`` into {columns:[str], rows:[[...]]} or None."""
    import json as _json

    if isinstance(data, str):
        try:
            data = _json.loads(data)
        except Exception:  # noqa: BLE001
            return None
    rows = cols = None
    if isinstance(data, dict):
        cols = data.get("columns") or data.get("schema")
        rows = data.get("rows") or data.get("data")
        if isinstance(cols, list) and cols and isinstance(cols[0], dict):
            cols = [c.get("field") or c.get("name") or c.get("headerName") or c.get("generated_column_name") for c in cols]
    elif isinstance(data, list):
        rows = data
        if rows and isinstance(rows[0], dict):
            cols = list(rows[0].keys())
    if not rows:
        return None
    if not cols and isinstance(rows[0], dict):
        cols = list(rows[0].keys())
    cols = [str(c) for c in (cols or [])]
    # normalise array-of-objects → array-of-arrays aligned to cols
    out_rows = []
    for r in rows[:_WORKBOOK_MAX_ROWS]:
        if isinstance(r, dict):
            out_rows.append([r.get(c) for c in cols])
        elif isinstance(r, (list, tuple)):
            out_rows.append(list(r))
        else:
            out_rows.append([r])
    return {"columns": cols, "rows": out_rows}


@router.get("/reports/{report_id}/workbook")
async def get_report_workbook(
    report_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Return ``{sheets:[{name,columns,rows}]}`` — one sheet per query's latest
    success step. Read-only, fail-soft, gated by the same flag."""
    _ensure_enabled()
    report = await _load_report(db, report_id, organization)

    from app.models.query import Query
    from app.models.step import Step
    try:
        from app.services.parquet_store import hydrate as _hydrate
    except Exception:  # noqa: BLE001
        _hydrate = lambda d: d  # noqa: E731

    queries = (
        await db.execute(
            select(Query).where(Query.report_id == report.id).order_by(Query.created_at.asc())
        )
    ).scalars().all()

    sheets: list[dict] = []
    for q in queries:
        if len(sheets) >= _WORKBOOK_MAX_SHEETS:
            break
        step = None
        if getattr(q, "default_step_id", None):
            step = await db.get(Step, q.default_step_id)
        if step is None or (step.status or "") != "success" or not step.data:
            step = (
                await db.execute(
                    select(Step).where(Step.query_id == q.id, Step.status == "success")
                    .order_by(desc(Step.created_at)).limit(1)
                )
            ).scalar_one_or_none()
        if step is None or not step.data:
            continue
        try:
            sd = _hydrate(step.data)
        except Exception:  # noqa: BLE001
            sd = step.data
        grid = _coerce_grid(sd)
        if not grid:
            continue
        name = (q.title or step.title or f"Sheet {len(sheets) + 1}")[:28]
        sheets.append({"name": name, "columns": grid["columns"], "rows": grid["rows"]})

    # Sense-Making "Insights" sheet (deterministic, NO LLM) — prepend at index 0
    # so it's the first tab. Flag-gated + fully fail-soft: any error → original sheets.
    if flags.SENSE_MAKING:
        try:
            from app.ai.knowledge.sense_maker import get_stored_sense_making

            sm = await get_stored_sense_making(db, str(report.id))
            if sm:
                insight_rows: list[list[str]] = []
                headline = sm.get("headline") or {}
                insight_rows.append(["Headline", str(headline.get("text") or "")])
                _sev = str(headline.get("severity") or "")
                _conf = str(headline.get("confidence") or "")
                insight_rows.append(["Severity", f"{_sev} · confidence {_conf}"])
                for f in (sm.get("findings") or [])[:6]:
                    if not isinstance(f, dict):
                        continue
                    nw = f.get("now_what") or {}
                    rank = str(nw.get("impact_rank") or "")
                    kind = str(f.get("kind") or "")
                    insight_rows.append([
                        f"#{rank} {kind}".strip(),
                        f"{f.get('what') or ''} → {nw.get('action') or ''}",
                    ])
                for a in (sm.get("alerts") or [])[:6]:
                    if not isinstance(a, dict):
                        continue
                    insight_rows.append([
                        "Alert",
                        f"{a.get('metric') or ''} {a.get('value') or ''} vs "
                        f"{a.get('threshold') or ''} → {a.get('action') or ''}",
                    ])
                insight_rows = [[str(c) for c in row] for row in insight_rows]
                sheets.insert(0, {
                    "name": "Insights",
                    "columns": ["Decision", "Detail"],
                    "rows": insight_rows,
                })
        except Exception:  # noqa: BLE001 — never break the workbook
            logger.warning("Insights sheet build failed for report %s", report_id, exc_info=True)

    return {"sheets": sheets}


# --------------------------------------------------------------------------- #
# Session Summary — one cached cheap-LLM roll-up across ALL turns of a report.
# Gated by the org setting ``session_summary`` (default ON), NOT a hybrid flag.
# GET  /api/reports/{id}/session-summary → {summary, stale}  (NO rebuild)
# POST /api/reports/{id}/session-summary → rebuild + cache, returns {summary, stale}
# Fully fail-soft: errors degrade to {summary:null, ...}, never a raw 500.
# --------------------------------------------------------------------------- #


async def _session_summary_enabled(db: AsyncSession, organization) -> bool:
    """Read the org ``session_summary`` setting (default ON). Fail-soft → True."""
    try:
        from app.models.organization_settings import OrganizationSettings

        row = (
            await db.execute(
                select(OrganizationSettings).where(
                    OrganizationSettings.organization_id == organization.id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return True  # no settings row yet → schema default (ON)
        cfg = row.get_config("session_summary")
        if cfg is None:
            return True
        val = cfg.value if hasattr(cfg, "value") else cfg
        return bool(val)
    except Exception:  # noqa: BLE001 — never break the route on a settings read
        logger.warning("session_summary: settings read failed", exc_info=True)
        return True


def _is_stale(summary, marker: dict) -> bool:
    """stale=True when there is no summary, or its provenance differs from the
    report's CURRENT latest system completion (count or last id)."""
    if not isinstance(summary, dict):
        return True
    gf = summary.get("generated_from") if isinstance(summary.get("generated_from"), dict) else {}
    return (
        gf.get("completion_count") != marker.get("completion_count")
        or gf.get("last_completion_id") != marker.get("last_completion_id")
    )


@router.get("/reports/{report_id}/session-summary")
async def get_report_session_summary(
    report_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Return the cached session summary + whether it's stale. NEVER rebuilds."""
    if not await _session_summary_enabled(db, organization):
        return {"summary": None, "stale": False}

    report = await _load_report(db, report_id, organization)
    try:
        from app.ai.knowledge.session_summary import latest_completion_marker

        marker = await latest_completion_marker(db, str(report.id))
        summary = report.session_summary
        return {"summary": summary, "stale": _is_stale(summary, marker)}
    except Exception:  # noqa: BLE001 — fail-soft read
        logger.warning("session_summary GET failed for report %s", report_id, exc_info=True)
        return {"summary": report.session_summary, "stale": True}


@router.post("/reports/{report_id}/session-summary")
async def rebuild_report_session_summary(
    report_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Rebuild the session summary via the cheap-LLM synthesizer, cache it on the
    report, and return it. No-op (200, {summary:null}) when the setting is OFF."""
    if not await _session_summary_enabled(db, organization):
        return {"summary": None, "stale": False}

    report = await _load_report(db, report_id, organization)
    try:
        from datetime import datetime, timezone
        from sqlalchemy.orm.attributes import flag_modified
        from app.ai.knowledge.session_summary import build_session_summary
        from app.services.llm_service import LLMService

        # Cheap/small org default model — same tier as sense_maker / followups.
        model = await LLMService().get_default_model(
            db, organization, current_user, is_small=True
        )

        summary = await build_session_summary(
            db, report=report, organization=organization,
            user=current_user, model=model,
        )
        if not summary:
            # Nothing to summarise (no completed turns) or synth failed — fail-soft.
            return {"summary": report.session_summary, "stale": True}

        # Stamp the provenance timestamp the synthesizer left as None.
        gf = summary.get("generated_from")
        if isinstance(gf, dict):
            gf["generated_at"] = datetime.now(timezone.utc).isoformat()

        report.session_summary = summary
        flag_modified(report, "session_summary")  # JSON in-place set isn't auto-tracked
        await db.commit()
        return {"summary": summary, "stale": False}
    except Exception:  # noqa: BLE001 — never leak a raw 500
        logger.warning("session_summary POST failed for report %s", report_id, exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"summary": report.session_summary, "stale": True}
