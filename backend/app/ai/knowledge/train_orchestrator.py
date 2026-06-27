"""Async studio Auto-train orchestrator.

Today the Studio "Auto-train" flow runs profiling + auto-queries + auto-evals +
artifact generation SEQUENTIALLY from the front-end, blocking the request for
~30-90s. This module moves that work into a fire-and-forget background task and
exposes an in-process status dict the FE can poll.

Design (mirrors the hybrid brain-worker discipline used elsewhere in the repo):
  * In-process status store ``_RUNS`` keyed by ``studio_id`` (like
    ``routes/workflows.py`` ``_LAST_RUNS``). No persistence table — runs are
    ephemeral; an empty/idle status is fine.
  * The background coroutine opens its OWN fresh async session
    (``async_session_maker``) — the request session is already closed by the
    time it runs. Org + User are reloaded by PK inside that session (they may be
    detached / belong to the request session).
  * Every stage is wrapped in try/except: a stage failure is recorded in
    ``detail`` and the next stage still runs. The task NEVER raises.
  * The created ``asyncio.Task`` is kept in a module-level list ``_TASKS`` so the
    event loop doesn't garbage-collect it mid-flight (the classic
    ``asyncio.create_task`` weak-reference landmine).

Status shape (``get_status``):
  ``{"status": "running"|"done"|"error"|"idle",
     "step": <str>, "pct": <int>, "detail": {<stage>: <ok|error msg>},
     "error": <str only when status=='error'>}``

Reuses existing services — does NOT re-implement any of them:
  profiling  -> ``routes.column_profile._profile_all_tables`` (canonical loop)
  queries    -> ``ai.knowledge.auto_queries.generate_queries_for_studio``
  evals      -> ``ai.knowledge.auto_evals.generate_evals_for_studio``
  artifacts  -> ``services.studio_artifacts.generate_artifact`` (persisted as
                ``StudioArtifact`` rows, mirroring the generate route).
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

logger = logging.getLogger(__name__)

# In-process status store, keyed by studio_id. Survives only the process
# lifetime; per-uvicorn-worker (like the other hybrid in-process stores).
_RUNS: dict = {}

# Strong references to scheduled tasks so the loop doesn't GC them mid-flight.
_TASKS: list = []

# Artifact kinds generated during a train run (every GENERATED_KINDS member).
_ARTIFACT_KINDS = ("summary", "faq", "briefing", "notes", "kpi_pack", "data_dictionary")


def get_status(studio_id) -> dict:
    """Return the current/last status for a studio's train run, or idle."""
    return _RUNS.get(str(studio_id), {"status": "idle"})


def _set(studio_id, **kw) -> None:
    """Merge keys into the studio's status entry (in place)."""
    cur = _RUNS.get(str(studio_id))
    if not isinstance(cur, dict):
        cur = {}
        _RUNS[str(studio_id)] = cur
    cur.update(kw)


# --- Claude-Code-style live log -------------------------------------------
# Each run keeps a rolling buffer of timestamped log lines (capped). Lines come
# from (a) explicit _log() calls at stage/LLM boundaries and (b) a logging
# handler that captures everything the trainer + LLM client already emit, so the
# panel shows "which model / how many tokens / what saved" without threading
# state through every call site.
_LOG_CAP = 400          # max lines kept in-process
_LOG_PERSIST_CAP = 200  # max lines mirrored to the DB (bound JSON size)


def _log(studio_id, msg, level: str = "info") -> None:
    """Append one timestamped line to the run's log buffer (capped)."""
    sid = str(studio_id)
    cur = _RUNS.get(sid)
    if not isinstance(cur, dict):
        return
    buf = cur.get("log")
    if not isinstance(buf, list):
        buf = []
        cur["log"] = buf
    try:
        ts = datetime.now().strftime("%H:%M:%S.") + f"{datetime.now().microsecond // 100000}"
    except Exception:  # noqa: BLE001
        ts = ""
    buf.append({"t": ts, "lvl": level, "msg": str(msg)[:500]})
    if len(buf) > _LOG_CAP:
        del buf[: len(buf) - _LOG_CAP]


class _RunLogHandler(logging.Handler):
    """Routes log records emitted DURING a run into that run's log buffer.

    Attached to the trainer + LLM loggers for the run's lifetime, detached in
    finally. Maps Python levels to our cli levels (error/warn/info)."""

    def __init__(self, sid: str):
        super().__init__(level=logging.INFO)
        self._sid = sid

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            if record.levelno >= logging.ERROR:
                lvl = "error"
            elif record.levelno >= logging.WARNING:
                lvl = "warn"
            else:
                lvl = "info"
            msg = record.getMessage()
            # strip the noisy module-prefix the trainer prepends
            if msg.startswith("train_orchestrator "):
                msg = msg[len("train_orchestrator "):]
            _log(self._sid, msg, lvl)
        except Exception:  # noqa: BLE001 - logging must never raise
            pass


# Logger names whose records we capture into the live log during a run.
_CAPTURE_LOGGERS = ("app.ai.knowledge", "app.ai.llm", __name__)


def _attach_log_capture(sid: str):
    """Attach a capture handler to the trainer/LLM loggers; return (handler,
    [loggers]) so the caller can detach in finally."""
    handler = _RunLogHandler(sid)
    attached = []
    for name in _CAPTURE_LOGGERS:
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            # ensure INFO records reach the handler without changing global config
            lg.setLevel(logging.INFO)
        attached.append(lg)
    return handler, attached


def _detach_log_capture(handler, loggers) -> None:
    for lg in loggers or []:
        try:
            lg.removeHandler(handler)
        except Exception:  # noqa: BLE001
            pass


def reset_status(studio_id) -> None:
    """Drop any in-process status/log for a studio (used by the reset route)."""
    _RUNS.pop(str(studio_id), None)


async def _persist_db(db, studio, sid) -> None:
    """Mirror the in-process status onto Studio.config['_train_status'] so it is
    visible across uvicorn workers (the in-process _RUNS is per-process). Cheap,
    called at stage boundaries. Fail-soft."""
    try:
        from sqlalchemy.orm.attributes import flag_modified

        cfg = studio.config if isinstance(studio.config, dict) else {}
        cfg = dict(cfg)
        snap = dict(_RUNS.get(str(sid), {}))
        # mirror only the tail of the log to bound the persisted JSON size
        if isinstance(snap.get("log"), list) and len(snap["log"]) > _LOG_PERSIST_CAP:
            snap["log"] = snap["log"][-_LOG_PERSIST_CAP:]
        cfg["_train_status"] = snap
        studio.config = cfg
        flag_modified(studio, "config")
        await db.commit()
    except Exception:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:
            pass


async def _load_studio(db, studio_id):
    from app.models.studio import Studio

    res = await db.execute(
        select(Studio).where(
            Studio.id == studio_id,
            Studio.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def _resolve_pinned_sources(db, studio, organization):
    """Resolve a studio's pinned DataSources (org-scoped). Mirrors
    ``services.studio_artifacts._gather_pinned_sources``; returns [] on failure."""
    try:
        from app.models.data_source import DataSource
        from app.models.studio import StudioDataSource

        org_id = getattr(organization, "id", None) or getattr(
            studio, "organization_id", None
        )
        res = await db.execute(
            select(StudioDataSource)
            .where(
                StudioDataSource.studio_id == studio.id,
                StudioDataSource.deleted_at.is_(None),
            )
            .order_by(StudioDataSource.created_at.asc())
        )
        pins = list(res.scalars().all())
        if not pins:
            return []
        agent_ids = [p.agent_id for p in pins]
        ds_res = await db.execute(
            select(DataSource).where(
                DataSource.id.in_(agent_ids),
                DataSource.organization_id == org_id,
            )
        )
        return list(ds_res.scalars().all())
    except Exception as e:  # noqa: BLE001 - fail-soft
        logger.warning("train_orchestrator pinned-source resolution failed: %s", e)
        return []


async def run_training(studio_id, organization_id, user_id) -> None:
    """Run the full studio auto-train pipeline in the background. NEVER raises.

    Opens its own fresh session, reloads org/user/studio by PK, then runs the
    stages (profile -> queries -> evals -> artifacts), updating ``_RUNS`` after
    each. A stage error is recorded in ``detail`` and the run continues.
    """
    sid = str(studio_id)
    _RUNS[sid] = {
        "status": "running",
        "step": "starting",
        "pct": 5,
        "started_at": datetime.utcnow().isoformat(),
        "detail": {},
        "log": [],
    }
    _log_handler, _log_loggers = _attach_log_capture(sid)
    _log(sid, "Auto-train started", "info")

    try:
        from app.dependencies import async_session_maker
        from app.models.organization import Organization
        from app.models.user import User
    except Exception as e:  # noqa: BLE001 - cannot even import deps
        _RUNS[sid] = {"status": "error", "error": f"import failed: {e}"}
        return

    try:
        async with async_session_maker() as db:
            # Reload org / user / studio by PK in THIS session.
            organization = (
                await db.execute(
                    select(Organization).where(Organization.id == organization_id)
                )
            ).scalar_one_or_none()
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            studio = await _load_studio(db, studio_id)

            if studio is None or organization is None:
                _RUNS[sid] = {
                    "status": "error",
                    "error": "studio or organization not found",
                }
                return

            detail = _RUNS[sid]["detail"]
            # Resolve pinned sources ONCE — reused across profiling + joins stages.
            sources = await _resolve_pinned_sources(db, studio, organization)
            _log(sid, f"studio '{getattr(studio, 'name', sid)}' · {len(sources)} pinned source(s)", "info")
            try:
                from app.services.llm_service import LLMService as _LLMSvc0
                _dm = await _LLMSvc0().get_default_model(db, organization)
                _dm_name = getattr(_dm, "model_id", None) or getattr(_dm, "name", None) or str(_dm)
                _log(sid, f"default analysis model: {_dm_name}", "info")
            except Exception as _dme:  # noqa: BLE001 - fail-soft, model is informational
                _log(sid, f"could not resolve default model: {_dme}", "warn")

            # --- Stage 1: profile all pinned sources (pct 10 -> 40) -----------
            # Profiling N tables × many columns against a live connector can take
            # minutes; without intra-stage feedback the UI looks frozen at 10%.
            # A per-table progress callback interpolates pct across the 10..40
            # slice and writes a human note ("RTM · 3/8 tables"), so the bar moves.
            _set(sid, step="profiling", pct=10, note="starting")
            _log(sid, "▸ profile columns", "info")
            try:
                from app.routes.column_profile import _profile_all_tables

                profiled = 0
                n_src = max(1, len(sources))
                for si, ds in enumerate(sources):
                    ds_name = getattr(ds, "name", None) or str(getattr(ds, "id", "?"))[:8]
                    base = 10 + int(30 * si / n_src)      # this source's slice start
                    span = 30 / n_src                      # pct width for this source

                    def _on_table(done, total, table, written, _base=base, _span=span, _name=ds_name):
                        pct = int(_base + _span * (done / max(1, total)))
                        _set(sid, pct=min(39, max(10, pct)),
                             note=f"{_name} · {done}/{total} tables")

                    try:
                        # Hard ceiling per source: a hung remote query (no
                        # statement_timeout) must not freeze the train forever.
                        written, _u, reports, _rows, _n = await asyncio.wait_for(
                            _profile_all_tables(db, ds, str(ds.id), progress=_on_table),
                            timeout=600,
                        )
                        if reports:
                            profiled += 1
                        logger.info("train_orchestrator profiled %s: %s cols, %s tables",
                                    ds_name, written, _n)
                    except asyncio.TimeoutError:
                        logger.warning("train_orchestrator profile TIMEOUT (600s) for %s", ds_name)
                        _set(sid, note=f"{ds_name} · timed out, skipped")
                    except Exception as e:  # noqa: BLE001 - per-source fail-soft
                        logger.warning(
                            "train_orchestrator profile failed for %s: %s",
                            getattr(ds, "id", "?"),
                            e,
                        )
                await db.commit()
                detail["profiling"] = f"ok ({profiled}/{len(sources)} sources)"
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["profiling"] = f"error: {e}"
            _set(sid, pct=40, note="")
            await _persist_db(db, studio, sid)

            # --- Stage 1a: deep profile v2 (Wave1 P1) -------------------------
            # When flags.PROFILE_V2 is ON, run profile_table_v2 on every active
            # table of each source AFTER the column profiler has written its data.
            # Mirrors the Stage 4b (semantic_metrics) pattern: per-source fail-soft,
            # single commit at the end.  Zero DB reads / writes when flag is OFF.
            from app.settings.hybrid_flags import flags as _flags

            if _flags.PROFILE_V2:
                _set(sid, step="profile_v2", pct=41)
                _log(sid, "▸ deep profile", "info")
                try:
                    from sqlalchemy import select as _sel
                    from app.models.datasource_table import DataSourceTable as _DST
                    from app.ai.knowledge.profile_v2 import profile_table_v2 as _pv2

                    pv2_count = 0
                    for ds in sources:
                        try:
                            tbl_rows = list(
                                (
                                    await db.execute(
                                        _sel(_DST)
                                        .where(_DST.datasource_id == str(ds.id))
                                        .where(_DST.is_active.is_(True))
                                    )
                                ).scalars().all()
                            )
                            for tbl_row in tbl_rows:
                                try:
                                    _pv2(tbl_row)
                                    pv2_count += 1
                                except Exception as _te:  # noqa: BLE001
                                    logger.debug(
                                        "train_orchestrator profile_v2 table %s: %s",
                                        getattr(tbl_row, "name", "?"),
                                        _te,
                                    )
                        except Exception as _se:  # noqa: BLE001 - per-source fail-soft
                            logger.warning(
                                "train_orchestrator profile_v2 source %s: %s",
                                getattr(ds, "id", "?"),
                                _se,
                            )
                    await db.commit()
                    detail["profile_v2"] = f"ok ({pv2_count} tables)"
                except Exception as e:  # noqa: BLE001
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    detail["profile_v2"] = f"error: {e}"

            # --- Stage 1b: code enrich (Wave1 P6) --------------------------------
            # When flags.CODE_ENRICH is ON, fetch view/table DDL for each active
            # table and LLM-extract grain + derived-column formulas + population.
            # Stores in metadata_json['pipeline_logic'].  Mirrors Stage 1a pattern.
            # Zero DB reads/writes when flag is OFF.
            if _flags.CODE_ENRICH:
                _set(sid, step="code_enrich", pct=42)
                _log(sid, "▸ code enrich", "info")
                try:
                    from app.ai.knowledge.code_enrich import enrich_source
                    from app.services.llm_service import LLMService as _LLMSvc

                    _ce_model = await _LLMSvc().get_default_model(
                        db, organization, user, is_small=True
                    )
                    ce_enriched = 0
                    ce_skipped = 0
                    for ds in sources:
                        try:
                            r = await enrich_source(
                                db,
                                data_source=ds,
                                organization=organization,
                                model=_ce_model,
                            )
                            ce_enriched += int((r or {}).get("enriched", 0) or 0)
                            ce_skipped += int((r or {}).get("skipped", 0) or 0)
                        except Exception as _ce_err:  # noqa: BLE001 - per-source fail-soft
                            logger.warning(
                                "train_orchestrator code_enrich failed for %s: %s",
                                getattr(ds, "id", "?"),
                                _ce_err,
                            )
                    detail["code_enrich"] = f"ok ({ce_enriched} enriched, {ce_skipped} skipped)"
                except Exception as e:  # noqa: BLE001
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    detail["code_enrich"] = f"error: {e}"

            # --- Stage 1c: pack autobind (Phase 4) ----------------------------
            # Try every library pack against the freshly-profiled columns; write
            # pending/dormant StudioBoundPack rows. Then render the studio's ACTIVE
            # skills into a context block that biases the query/eval generators.
            _set(sid, step="packs", pct=42)
            _log(sid, "▸ bind domain packs", "info")
            skill_context = ""
            try:
                from app.ai.packs.pack_train import (
                    autobind_library_packs,
                    recheck_bindings,
                    build_skill_context,
                )

                detail["packs"] = await autobind_library_packs(db, sid, organization)
                # Phase 5: re-check existing rows vs the just-profiled schema
                # (dormant->pending if a missing column appeared; active->dormant
                # if a bound column vanished).
                detail["pack_recheck"] = await recheck_bindings(db, sid)
                skill_context = await build_skill_context(db, sid)
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["packs"] = f"error: {e}"
            _set(sid, pct=44)

            # --- Stage 2: auto-queries (pct 60) -------------------------------
            _set(sid, step="queries", pct=45)
            _log(sid, "▸ write example queries", "info")
            try:
                from app.ai.knowledge.auto_queries import generate_queries_for_studio

                qres = await generate_queries_for_studio(
                    db,
                    organization=organization,
                    current_user=user,
                    studio_id=sid,
                    skill_context=skill_context,
                )
                detail["queries"] = qres
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["queries"] = f"error: {e}"
            _set(sid, pct=60)

            # --- Stage 3: auto-evals (pct 75) ---------------------------------
            _set(sid, step="evals", pct=65)
            _log(sid, "▸ write eval goldens", "info")
            try:
                from app.ai.knowledge.auto_evals import generate_evals_for_studio

                eres = await generate_evals_for_studio(
                    db,
                    organization=organization,
                    current_user=user,
                    studio_id=sid,
                    skill_context=skill_context,
                )
                detail["evals"] = eres
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["evals"] = f"error: {e}"

            # --- Stage 3b: materialise pack-carried goldens (Phase 4) ---------
            try:
                from app.ai.packs.pack_train import materialize_pack_goldens

                detail["pack_goldens"] = await materialize_pack_goldens(
                    db, organization, sid
                )
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["pack_goldens"] = f"error: {e}"

            # --- Stage 3c: MINT goldens from each active pack's method (Phase C) -
            # Run the pack method's headline computation on real data → real
            # expected value → golden TestCase. Reuses the auto_evals machinery.
            try:
                from app.ai.packs.pack_goldens import mint_pack_goldens

                detail["pack_goldens_minted"] = await mint_pack_goldens(
                    db, organization, sid
                )
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["pack_goldens_minted"] = f"error: {e}"
            _set(sid, pct=75)
            await _persist_db(db, studio, sid)

            # --- Stage 4: artifacts loop (pct 95) -----------------------------
            _set(sid, step="artifacts", pct=80)
            _log(sid, "▸ generate artifacts", "info")
            artifacts = {}
            try:
                from app.models.studio import StudioArtifact
                from app.services.studio_artifacts import generate_artifact

                for kind in _ARTIFACT_KINDS:
                    try:
                        content = await generate_artifact(
                            db, studio, kind, organization=organization
                        )
                        row = StudioArtifact(
                            studio_id=sid, kind=kind, content=content
                        )
                        db.add(row)
                        await db.commit()
                        artifacts[kind] = "ok"
                    except Exception as e:  # noqa: BLE001 - per-kind fail-soft
                        try:
                            await db.rollback()
                        except Exception:
                            pass
                        artifacts[kind] = f"error: {e}"
                detail["artifacts"] = artifacts
            except Exception as e:  # noqa: BLE001
                detail["artifacts"] = f"error: {e}"
            _set(sid, pct=92)

            # --- Stage 4b: semantic layer + metrics catalog (pct 93) ----------
            # Opt-in surfaces. Only runs when a flag is on. Proposals are AI-
            # pending; auto-approved here (like every other Auto-train stage) so
            # the Semantic / Metrics tabs are populated AND live after the one-
            # button train instead of sitting empty.
            from app.settings.hybrid_flags import flags as _flags

            if _flags.SEMANTIC_LAYER or _flags.METRICS_CATALOG:
                _set(sid, step="semantic_metrics", pct=93)
                _log(sid, "▸ semantic + metrics", "info")
                try:
                    from sqlalchemy import update as _sql_update

                    from app.ai.brain.knowledge_proposer import (
                        propose_column_meanings,
                        propose_knowledge_from_schema,
                    )
                    from app.models.metric_definition import MetricDefinition
                    from app.models.semantic_table import SemanticColumn, SemanticTable
                    from app.services.llm_service import LLMService

                    focus = (
                        "both"
                        if (_flags.SEMANTIC_LAYER and _flags.METRICS_CATALOG)
                        else ("semantic" if _flags.SEMANTIC_LAYER else "metrics")
                    )
                    model = await LLMService().get_default_model(
                        db, organization, user, is_small=True
                    )
                    sem_ids: list[str] = []
                    met_ids: list[str] = []
                    col_ids: list[str] = []
                    for ds in sources:
                        try:
                            r = await propose_knowledge_from_schema(
                                db,
                                organization=organization,
                                data_source=ds,
                                model=model,
                                focus=focus,
                            )
                        except Exception as e:  # noqa: BLE001 - per-source fail-soft
                            logger.warning(
                                "train_orchestrator semantic/metrics failed for %s: %s",
                                getattr(ds, "id", "?"),
                                e,
                            )
                            continue
                        sem_ids.extend((r or {}).get("semantics", []) or [])
                        met_ids.extend((r or {}).get("metrics", []) or [])
                        # Per-column meanings: only meaningful when SEMANTIC_LAYER is
                        # on. Fills blank SemanticColumn.meaning rows (pending), then
                        # we auto-approve below like every other Auto-train surface.
                        if _flags.SEMANTIC_LAYER:
                            try:
                                rc = await propose_column_meanings(
                                    db,
                                    organization=organization,
                                    data_source=ds,
                                    model=model,
                                )
                                col_ids.extend((rc or {}).get("columns", []) or [])
                            except Exception as e:  # noqa: BLE001 - per-source fail-soft
                                logger.warning(
                                    "train_orchestrator column meanings failed for %s: %s",
                                    getattr(ds, "id", "?"),
                                    e,
                                )

                    # Auto-approve the fresh proposals (Auto-train auto-approves;
                    # keeps the Review queue empty and the rows live in context).
                    if sem_ids:
                        await db.execute(
                            _sql_update(SemanticTable)
                            .where(SemanticTable.id.in_(sem_ids))
                            .values(status="approved")
                        )
                    if met_ids:
                        await db.execute(
                            _sql_update(MetricDefinition)
                            .where(MetricDefinition.id.in_(met_ids))
                            .values(status="approved")
                        )
                    if col_ids:
                        await db.execute(
                            _sql_update(SemanticColumn)
                            .where(SemanticColumn.id.in_(col_ids))
                            .values(status="approved")
                        )
                    if sem_ids or met_ids or col_ids:
                        await db.commit()
                    detail["semantic_metrics"] = (
                        f"ok ({len(sem_ids)} semantic, {len(met_ids)} metrics, "
                        f"{len(col_ids)} col meanings)"
                    )
                except Exception as e:  # noqa: BLE001
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    detail["semantic_metrics"] = f"error: {e}"
                _set(sid, pct=94)

            # --- Stage 5: value-overlap join mining (pct 98) ------------------
            # Proven-SQL joins need query history; value-overlap works on day 1.
            _set(sid, step="joins", pct=94)
            _log(sid, "▸ mine joins", "info")
            try:
                from app.ai.knowledge.join_miner import mine_value_overlap_edges

                mined = 0
                for ds in sources:
                    try:
                        r = await mine_value_overlap_edges(
                            db, organization=organization, data_source=ds
                        )
                        mined += int((r or {}).get("mined", 0) or 0)
                    except Exception as e:  # noqa: BLE001 - per-source fail-soft
                        logger.warning("train_orchestrator value-joins failed for %s: %s", getattr(ds, "id", "?"), e)
                detail["joins"] = f"ok ({mined} value-overlap edges)"
            except Exception as e:  # noqa: BLE001
                try:
                    await db.rollback()
                except Exception:
                    pass
                detail["joins"] = f"error: {e}"
            _set(sid, pct=98)

            # --- Done ---------------------------------------------------------
            _errs = [k for k, v in detail.items()
                     if (isinstance(v, str) and v.lower().startswith("error"))
                     or (isinstance(v, dict) and v.get("ok") is False)]
            if _errs:
                _log(sid, f"finished with {len(_errs)} failed stage(s): {', '.join(_errs)}", "warn")
            else:
                _log(sid, "all stages complete — agent ready", "info")
            _set(
                sid,
                status="done",
                step="done",
                pct=100,
                finished_at=datetime.utcnow().isoformat(),
            )
            await _persist_db(db, studio, sid)
    except Exception as e:  # noqa: BLE001 - fatal, never raise out of the task
        logger.warning("train_orchestrator fatal for studio %s: %s", sid, e)
        _log(sid, f"fatal: {e}", "error")
        _set(sid, status="error", step="error", error=str(e))
    finally:
        _detach_log_capture(_log_handler, _log_loggers)


def start_training(studio_id, organization_id, user_id) -> dict:
    """Schedule a background train run for a studio (idempotent per studio).

    If a run is already in progress for this studio, returns the current status
    instead of starting a second one. Otherwise seeds the initial ``_RUNS``
    entry, schedules ``run_training`` via ``asyncio.create_task`` and keeps a
    STRONG reference to the task (``_TASKS``) so it isn't GC'd.
    """
    sid = str(studio_id)
    cur = _RUNS.get(sid)
    if isinstance(cur, dict) and cur.get("status") == "running":
        return cur

    _RUNS[sid] = {
        "status": "running",
        "step": "starting",
        "pct": 5,
        "started_at": datetime.utcnow().isoformat(),
        "detail": {},
    }

    task = asyncio.create_task(run_training(studio_id, organization_id, user_id))
    _TASKS.append(task)
    # Drop the strong ref once the task is done so the list doesn't grow forever.
    task.add_done_callback(lambda t: _TASKS.remove(t) if t in _TASKS else None)

    return {"started": True, "status": "running", "studio_id": sid}
