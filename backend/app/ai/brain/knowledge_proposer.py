"""Self-learning knowledge write-back (Phase 5 BE).

When a user thumbs-down (👎) an answer, the distiller already turns the
correction into a PENDING, approval-gated Instruction. This module is the
KNOWLEDGE-LAYER sibling: from the same Q+A + correction context, it asks the
model to propose — when clearly grounded in the exchange — AT MOST:

  * (a) a per-table semantic description / use-case the answer revealed, and/or
  * (b) a named business metric (definition + sql_calc).

Each proposal lands as a ``status='pending'`` row on the existing knowledge
models (SemanticTable / MetricDefinition). The Phase-4 context builders inject
ONLY ``status=='approved'`` rows, so a ``pending`` proposal is automatically
invisible to the agent until an admin approves it in the UI.

Design rules honored (CLAUDE.md HARD RULES 3/4/5):
- Gated: runs ONLY when ``flags.DISTILLER`` AND (``flags.SEMANTIC_LAYER`` OR
  ``flags.METRICS_CATALOG``). Default OFF -> returns ``{}``, writes nothing.
- Everything proposed is approval-gated (``status='pending'``). NEVER
  auto-approved; we never touch an existing ``approved`` row.
- Reuses the distiller's feedback context (``gather_feedback_context`` /
  ``resolve_qa_pair``) — no new feedback path.
- LLM = the same one-shot inference signature the distiller uses (OpenRouter).
- Side-effect-light: every step is guarded; the public coroutine NEVER raises
  and degrades to a no-op so a 👎 never breaks the request path.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Provenance marker stamped on AI-proposed rows (matches existing column shapes:
# MetricDefinition.owner is a free string; SemanticTable has no owner column).
AI_OWNER = "ai-distiller"

# Provenance marker stamped on 👍-blessed proposals (Phase-3 "memory loop").
MEMORY_OWNER = "ai-memory-loop"

# Reject proposals whose text is too short to be a real description/definition.
_MIN_TEXT_LEN = 8


def build_propose_prompt(question: str, bad_answer: str, correction: Optional[str]) -> str:
    """Compose the one-shot knowledge-extraction prompt. Pure, deterministic.

    Asks the model to extract — ONLY if clearly grounded in the exchange — a
    table semantic description and/or a named metric. Strict single-line JSON
    output. The model is told to return empty fields when nothing is grounded.
    """
    correction_block = (
        f"User correction / what they actually wanted:\n{correction}\n\n"
        if correction
        else ""
    )
    return (
        "A user gave a thumbs-down to the analytics answer below. From this "
        "exchange, extract reusable KNOWLEDGE for the data catalog — but ONLY "
        "what is clearly and explicitly grounded in the question, the answer, "
        "or the correction. Do NOT invent tables, columns, metrics, or SQL that "
        "are not directly implied by the text.\n\n"
        f"Question:\n{question}\n\n"
        f"Bad answer (the one the user rejected):\n{bad_answer}\n\n"
        f"{correction_block}"
        "Return ONLY a single-line JSON object, no prose, no markdown, with this "
        "exact shape:\n"
        '{"semantic_table": {"table_name": "<name or empty>", "description": '
        '"<one-sentence meaning/use-case or empty>"}, '
        '"metric": {"name": "<metric name or empty>", "definition": '
        '"<one-sentence definition or empty>", "sql_calc": "<a single read-only '
        'SELECT/WITH statement or empty>", "table_ref": "<table the metric reads '
        'or empty>"}}\n\n'
        "Rules:\n"
        "- Propose a semantic_table ONLY if the exchange reveals what a specific "
        "named table means or is used for. Leave its fields empty otherwise.\n"
        "- Propose a metric ONLY if the exchange clearly defines a named business "
        "metric AND you can express it as one read-only SELECT/WITH. Leave its "
        "fields empty otherwise.\n"
        "- Never include both unless both are clearly grounded. Empty is fine — "
        "prefer proposing nothing over guessing.\n"
        "- Output the JSON object ONLY."
    )


def _parse_proposal(text: str) -> dict:
    """Best-effort parse the model's JSON. Tolerate junk -> empty dict."""
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    try:
        parsed = json.loads(cleaned, strict=False)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _clean(v: Any) -> str:
    return str(v or "").strip()


async def _resolve_data_source_id(db: Any, completion: Any) -> Optional[str]:
    """Resolve the completion's data source via report.data_sources.

    A completion -> report (``report_id``) -> ``report.data_sources`` (a
    many-to-many list). If the report links exactly one (or more) data sources,
    use the first. If none resolvable, return None (caller no-ops).
    """
    try:
        report_id = getattr(completion, "report_id", None)
        if not report_id:
            return None
        from app.models.report import Report

        report = await db.get(Report, str(report_id))
        if report is None:
            return None
        data_sources = getattr(report, "data_sources", None) or []
        for ds in data_sources:
            ds_id = getattr(ds, "id", None)
            if ds_id:
                return str(ds_id)
    except Exception:
        return None
    return None


async def _propose_semantic_table(
    db: Any, *, org_id: str, ds_id: str, table_name: str, description: str
) -> Optional[str]:
    """UPSERT a pending SemanticTable proposal. Returns its id, or None.

    - If an APPROVED row exists for (org, ds, table_name): do NOT overwrite it.
      Skip (the catalog already has a curated, approved meaning).
    - If a non-approved row exists (draft/pending/rejected): update it in place
      to carry the new proposed description and flip it to pending.
    - Otherwise: insert a new pending row.
    - Dedup: if an identical pending row already exists, return it (no dup).
    """
    from sqlalchemy import select
    from app.models.semantic_table import SemanticTable

    res = await db.execute(
        select(SemanticTable).where(
            SemanticTable.organization_id == org_id,
            SemanticTable.data_source_id == ds_id,
            SemanticTable.table_name == table_name,
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        if (existing.status or "") == "approved":
            return None  # never clobber an approved catalog row
        # Dedup: identical pending proposal already present.
        if (existing.status or "") == "pending" and (existing.description or "").strip() == description:
            return str(existing.id)
        existing.description = description
        existing.status = "pending"
        await db.flush()
        return str(existing.id)

    row = SemanticTable(
        organization_id=org_id,
        data_source_id=ds_id,
        table_name=table_name,
        description=description,
        use_cases=[],
        quality_notes=[],
        status="pending",
    )
    db.add(row)
    await db.flush()
    return str(row.id)


async def _propose_metric(
    db: Any,
    *,
    org_id: str,
    ds_id: str,
    name: str,
    definition: str,
    sql_calc: str,
    table_ref: str,
) -> Optional[str]:
    """UPSERT a pending MetricDefinition proposal. Returns its id, or None.

    Same approval-safe rules as the semantic upsert: never overwrite an approved
    metric; update a non-approved row to pending; else insert pending; dedup an
    identical pending proposal.
    """
    from sqlalchemy import select
    from app.models.metric_definition import MetricDefinition

    res = await db.execute(
        select(MetricDefinition).where(
            MetricDefinition.organization_id == org_id,
            MetricDefinition.data_source_id == ds_id,
            MetricDefinition.name == name,
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        if (existing.status or "") == "approved":
            return None  # never clobber an approved metric
        if (
            (existing.status or "") == "pending"
            and (existing.definition or "").strip() == definition
            and (existing.sql_calc or "").strip() == sql_calc
        ):
            return str(existing.id)  # identical pending dedup
        existing.definition = definition
        existing.sql_calc = sql_calc
        if table_ref:
            existing.table_ref = table_ref
        existing.owner = AI_OWNER
        existing.status = "pending"
        await db.flush()
        return str(existing.id)

    row = MetricDefinition(
        organization_id=org_id,
        data_source_id=ds_id,
        name=name,
        definition=definition,
        table_ref=table_ref,
        sql_calc=sql_calc,
        owner=AI_OWNER,
        status="pending",
    )
    db.add(row)
    await db.flush()
    return str(row.id)


async def propose_knowledge_from_completion(
    db: Any,
    *,
    organization: Any,
    user: Any,
    completion: Any,
    model: Any,
    llm_inference: Optional[Callable[[str], str]] = None,
) -> dict:
    """Propose pending semantic/metric knowledge from a 👎'd completion.

    Returns ``{'semantics': [...ids], 'metrics': [...ids]}`` (empty lists when
    nothing was written). Returns ``{}`` when gated off / no context / no data
    source. NEVER raises — every step is guarded and degrades to a no-op.
    """
    try:
        # 1. Flag gate: DISTILLER AND (SEMANTIC_LAYER OR METRICS_CATALOG).
        from app.settings.hybrid_flags import flags

        if not flags.DISTILLER:
            return {}
        want_semantic = bool(flags.SEMANTIC_LAYER)
        want_metric = bool(flags.METRICS_CATALOG)
        if not (want_semantic or want_metric):
            return {}

        # 2. Reuse the distiller's feedback context. Need question + bad answer.
        from app.ai.brain.distiller import gather_feedback_context

        ctx = await gather_feedback_context(db, completion)
        if not ctx.get("question") or not ctx.get("bad_answer"):
            return {}

        # 3. Resolve the data source (completion -> report -> data_sources).
        ds_id = await _resolve_data_source_id(db, completion)
        if not ds_id:
            return {}

        org_id = str(getattr(organization, "id", None) or "")
        if not org_id:
            return {}

        # 4. One-shot LLM proposal. Default: lazy-build the same call shape the
        #    distiller uses (OpenRouter via dash's LLM wrapper).
        infer = llm_inference
        if infer is None:
            def infer(p: str) -> str:  # noqa: E306 - tiny lazy default
                from app.ai.llm.llm import LLM
                from app.dependencies import async_session_maker

                return LLM(model, usage_session_maker=async_session_maker).inference(p)

        prompt = build_propose_prompt(ctx["question"], ctx["bad_answer"], ctx.get("correction"))
        raw = (infer(prompt) or "").strip()
        proposal = _parse_proposal(raw)
        if not proposal:
            return {}

        out: dict = {"semantics": [], "metrics": []}

        # 5a. Semantic table proposal (gated on SEMANTIC_LAYER).
        if want_semantic:
            st = proposal.get("semantic_table") or {}
            if isinstance(st, dict):
                table_name = _clean(st.get("table_name"))
                description = _clean(st.get("description"))
                if table_name and len(description) >= _MIN_TEXT_LEN:
                    new_id = await _propose_semantic_table(
                        db,
                        org_id=org_id,
                        ds_id=ds_id,
                        table_name=table_name,
                        description=description,
                    )
                    if new_id:
                        out["semantics"].append(new_id)

        # 5b. Metric proposal (gated on METRICS_CATALOG).
        if want_metric:
            m = proposal.get("metric") or {}
            if isinstance(m, dict):
                name = _clean(m.get("name"))
                definition = _clean(m.get("definition"))
                sql_calc = _clean(m.get("sql_calc"))
                table_ref = _clean(m.get("table_ref"))
                # Only propose a metric grounded enough to have a name + (a
                # definition or a SQL calc).
                if name and (len(definition) >= _MIN_TEXT_LEN or sql_calc):
                    new_id = await _propose_metric(
                        db,
                        org_id=org_id,
                        ds_id=ds_id,
                        name=name,
                        definition=definition,
                        sql_calc=sql_calc,
                        table_ref=table_ref,
                    )
                    if new_id:
                        out["metrics"].append(new_id)

        if out["semantics"] or out["metrics"]:
            await db.commit()
        return out
    except Exception as e:  # never break the request path on a 👎
        logger.warning("knowledge_proposer propose_knowledge_from_completion failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {}


# ---------------------------------------------------------------------------
# Phase-3 "👍 memory loop": when a user thumbs-UP an answer, promote the proven
# artifacts behind it as approval-gated knowledge:
#   * the captured SQL (from the QueryCache) -> a pending QueryLibraryItem, and
#   * bump the confidence of the auto-captured CodeCache the user just blessed.
# Same never-raise, lazy-import, approval-safe discipline as the 👎 path above.
# Gated by ``flags.MEMORY_LOOP`` (env HYBRID_MEMORY_LOOP); default OFF -> {}.
# ---------------------------------------------------------------------------


async def _propose_query_library(
    db: Any,
    *,
    org_id: str,
    ds_id: str,
    name: str,
    sql_text: str,
    description: str,
    question: str,
) -> Optional[str]:
    """UPSERT a pending QueryLibraryItem from a 👍'd SQL. Returns its id, or None.

    Mirrors ``_propose_metric``'s approval-safe rules, matched on the SQL text:
    - If an APPROVED row exists for (org, ds, sql_text): do NOT overwrite it
      (the library already has a curated, blessed query). Return None.
    - If an identical non-approved row is already ``pending``: return it (dedup).
    - If a non-approved row matches: update its name/description, flip to pending,
      stamp source='chat'/owner=MEMORY_OWNER. Return its id.
    - Otherwise: insert a new pending row. Return its id.
    Guarded: returns None on any failure (called inside the never-raise fn below).
    """
    try:
        from sqlalchemy import select
        from app.models.query_library import QueryLibraryItem

        res = await db.execute(
            select(QueryLibraryItem).where(
                QueryLibraryItem.organization_id == org_id,
                QueryLibraryItem.data_source_id == ds_id,
                QueryLibraryItem.sql_text == sql_text,
            )
        )
        existing = res.scalars().first()
        if existing is not None:
            if (existing.status or "") == "approved":
                return None  # never clobber an approved/curated query
            if (existing.status or "") == "pending":
                return str(existing.id)  # identical pending dedup
            existing.name = (name or "")[:120]
            existing.description = description
            existing.source = "chat"
            existing.owner = MEMORY_OWNER
            existing.status = "pending"
            await db.flush()
            return str(existing.id)

        row = QueryLibraryItem(
            organization_id=org_id,
            data_source_id=ds_id,
            name=(name or "")[:120],
            description=description,
            sql_text=sql_text,
            tags=["from-chat", "blessed"],
            source="chat",
            owner=MEMORY_OWNER,
            status="pending",
        )
        db.add(row)
        await db.flush()
        return str(row.id)
    except Exception:
        return None


async def propose_from_positive_completion(
    db: Any,
    *,
    organization: Any,
    user: Any,
    completion: Any,
    model: Any,
    llm_inference: Optional[Callable[[str], str]] = None,
) -> dict:
    """Promote proven artifacts from a 👍'd completion as pending knowledge.

    Returns ``{'queries': [...ids], 'code': [...ids]}`` (empty lists when nothing
    was written). Returns ``{}`` when gated off / no context / no data source.
    NEVER raises — every step is guarded and degrades to a no-op so a 👍 never
    breaks the request path.
    """
    try:
        # a. Flag gate: MEMORY_LOOP only.
        from app.settings.hybrid_flags import flags

        if not flags.MEMORY_LOOP:
            return {}

        # b. Reuse the distiller's feedback context. For a 👍 the 'bad_answer'
        #    field simply carries the blessed answer text. Need the question.
        from app.ai.brain.distiller import gather_feedback_context

        ctx = await gather_feedback_context(db, completion)
        if not ctx.get("question"):
            return {}

        # c. Resolve the data source + org.
        ds_id = await _resolve_data_source_id(db, completion)
        if not ds_id:
            return {}
        org_id = str(getattr(organization, "id", None) or "")
        if not org_id:
            return {}

        # d. Normalize the question -> hash (same keying as the query cache).
        from datetime import datetime

        from app.ai.brain.query_cache_store import (
            normalize_question,
            question_hash,
            is_read_only,
        )

        norm = normalize_question(ctx["question"])
        qhash = question_hash(norm)

        out: dict = {"queries": [], "code": []}

        from sqlalchemy import select

        # e. PROMOTE BLESSED SQL -> pending QueryLibraryItem. Read the captured
        #    SQL from the QueryCache regardless of its cache status.
        try:
            from app.models.query_cache import QueryCache

            res = await db.execute(
                select(QueryCache).where(
                    QueryCache.organization_id == org_id,
                    QueryCache.question_hash == qhash,
                    QueryCache.deleted_at.is_(None),
                    (
                        (QueryCache.data_source_id == ds_id)
                        | (QueryCache.data_source_id.is_(None))
                    ),
                ).order_by(QueryCache.hit_count.desc())
            )
            qc = res.scalars().first()
            if qc is not None and qc.sql_text and is_read_only(qc.sql_text):
                qid = await _propose_query_library(
                    db,
                    org_id=org_id,
                    ds_id=ds_id,
                    name=ctx["question"],
                    sql_text=qc.sql_text,
                    description="Confirmed from a 👍'd chat answer.",
                    question=ctx["question"],
                )
                if qid:
                    out["queries"].append(qid)

                # Golden promotion: a thumbs-up is a strong verification signal.
                # If an approved query_library row already holds this SQL, bump
                # its verified_count and promote to golden when threshold is met.
                # Gated on GOLDEN_QUERIES — no-op when flag is OFF.
                try:
                    from app.ai.knowledge.query_learning import promote_to_golden
                    from app.models.query_library import QueryLibraryItem

                    gq_res = await db.execute(
                        select(QueryLibraryItem).where(
                            QueryLibraryItem.organization_id == org_id,
                            QueryLibraryItem.data_source_id == ds_id,
                            QueryLibraryItem.sql_text == qc.sql_text,
                            QueryLibraryItem.status == "approved",
                            QueryLibraryItem.deleted_at.is_(None),
                        )
                    )
                    gq_row = gq_res.scalars().first()
                    if gq_row is not None:
                        await promote_to_golden(db, item=gq_row, reason="thumbs-up")
                except Exception:
                    pass  # never break the thumbs-up path
        except Exception:
            pass  # no hard dependency on the query cache

        # f. BLESS CODE MEMORY — bump the confidence of the auto-captured code
        #    the user just blessed (no status change; it is already 'active').
        try:
            from app.models.code_cache import CodeCache

            res = await db.execute(
                select(CodeCache).where(
                    CodeCache.organization_id == org_id,
                    CodeCache.question_hash == qhash,
                    CodeCache.deleted_at.is_(None),
                    (
                        (CodeCache.data_source_id == ds_id)
                        | (CodeCache.data_source_id.is_(None))
                    ),
                ).order_by(CodeCache.hit_count.desc())
            )
            cc = res.scalars().first()
            if cc is not None:
                cc.hit_count = (cc.hit_count or 0) + 1
                cc.last_used_at = datetime.utcnow()
                out["code"].append(str(cc.id))
        except Exception:
            pass

        # g. Commit only if we wrote something.
        if out["queries"] or out["code"]:
            await db.commit()
        return out
    except Exception as e:  # never break the request path on a 👍
        logger.warning("knowledge_proposer propose_from_positive_completion failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {}


# ---------------------------------------------------------------------------
# Phase-7 "AI-suggest": propose pending knowledge by INTROSPECTING a data
# source's schema (no 👎 needed). Reuses the same approval-safe upsert helpers
# above, so everything lands as status='pending' and shows up in the Review tab.
# ---------------------------------------------------------------------------

# Prompt-size bounds for schema introspection.
_MAX_SCHEMA_TABLES = 40
_MAX_SCHEMA_COLS = 30


def _introspect_schema_text(data_source: Any) -> tuple[str, set[str]]:
    """Build a compact ``table(col1, col2, ...)`` schema text + a set of the
    table names that actually exist. Guarded: returns ("", set()) on any failure.
    """
    try:
        client = data_source.get_client()
        tables = client.get_schemas() or []
    except Exception:
        return "", set()

    lines: list[str] = []
    names: set[str] = set()
    try:
        for table in list(tables)[:_MAX_SCHEMA_TABLES]:
            tname = _clean(getattr(table, "name", None))
            if not tname:
                continue
            names.add(tname)
            cols = getattr(table, "columns", None) or []
            col_names: list[str] = []
            for col in cols[:_MAX_SCHEMA_COLS]:
                cn = _clean(getattr(col, "name", None) or (col.get("name") if isinstance(col, dict) else None))
                if cn:
                    col_names.append(cn)
            lines.append(f"{tname}({', '.join(col_names)})")
    except Exception:
        return "", set()

    return "\n".join(lines), names


def build_schema_suggest_prompt(schema_text: str, focus: str) -> str:
    """Compose the strict-JSON schema-introspection extraction prompt.

    Honors ``focus`` in {'semantic','metrics','both'} — when focused, the model
    is told to leave the other section empty.
    """
    want_semantic = focus in ("semantic", "both")
    want_metric = focus in ("metrics", "both")
    sem_rule = (
        "- semantic_tables: up to 8 entries, each {\"table_name\": \"<MUST be a "
        "table that appears verbatim in the schema>\", \"description\": \"<one "
        "concise sentence describing the business meaning / use of that table>\"}. "
        "Only describe tables you can clearly infer a meaning for.\n"
        if want_semantic
        else "- semantic_tables: return an empty list [].\n"
    )
    metric_rule = (
        "- metrics: up to 6 entries, each {\"name\": \"<short metric name>\", "
        "\"definition\": \"<one-sentence business definition>\", \"sql_calc\": "
        "\"<a SINGLE read-only SELECT statement over the schema's tables>\", "
        "\"table_ref\": \"<the primary table the metric reads>\"}. Propose only "
        "metrics that are clearly expressible from the schema.\n"
        if want_metric
        else "- metrics: return an empty list [].\n"
    )
    return (
        "You are a data catalog assistant. Below is the schema of a data source "
        "as a list of `table(col1, col2, ...)` lines. Propose reusable catalog "
        "KNOWLEDGE grounded ONLY in this schema. Do NOT invent tables or columns "
        "that are not present.\n\n"
        f"Schema:\n{schema_text}\n\n"
        "Return ONLY a single-line JSON object, no prose, no markdown, with this "
        "exact shape:\n"
        '{"semantic_tables": [{"table_name": "...", "description": "..."}], '
        '"metrics": [{"name": "...", "definition": "...", "sql_calc": "...", '
        '"table_ref": "..."}]}\n\n'
        "Rules:\n"
        f"{sem_rule}"
        f"{metric_rule}"
        "- Prefer proposing fewer, high-confidence items over guessing.\n"
        "- Output the JSON object ONLY."
    )


def build_column_meaning_prompt(
    table_name: str, description: str, columns: list[str]
) -> str:
    """Compose the strict-JSON per-column meaning prompt. Pure, deterministic.

    Given a table (+ optional description) and a list of ``col (type)`` strings
    whose meaning is still blank, ask the model for a ONE-sentence business
    meaning per column — grounded ONLY in the column/table names, no invention.
    Returns a single-line JSON object mapping each column name to its meaning.
    """
    desc_block = f"Table description: {description}\n" if description else ""
    cols_block = "\n".join(f"- {c}" for c in columns)
    return (
        "You are a data catalog assistant. Below is one table and the columns "
        "whose business meaning is still missing. For EACH listed column, write a "
        "single concise sentence describing what it most likely means, grounded "
        "ONLY in the column name and the table context. Do NOT invent columns — "
        "describe ONLY the columns listed.\n\n"
        f"Table: {table_name}\n"
        f"{desc_block}"
        "Columns needing a meaning:\n"
        f"{cols_block}\n\n"
        "Return ONLY a single-line JSON object, no prose, no markdown, mapping "
        "each column name to its one-sentence meaning, e.g.\n"
        '{"site": "Physical location/site where the reading was taken", '
        '"reading_ts": "Timestamp at which the reading was recorded"}\n\n'
        "Rules:\n"
        "- Include a key for EVERY column listed above, and ONLY those columns.\n"
        "- Each value = ONE concise sentence, no markdown.\n"
        "- Output the JSON object ONLY."
    )


def _parse_suggest_proposal(text: str) -> dict:
    """Parse the schema-suggest JSON. Tolerant -> empty lists on junk."""
    parsed = _parse_proposal(text)  # reuse the tolerant brace-extraction parser
    if not isinstance(parsed, dict):
        return {"semantic_tables": [], "metrics": []}
    sem = parsed.get("semantic_tables")
    met = parsed.get("metrics")
    return {
        "semantic_tables": sem if isinstance(sem, list) else [],
        "metrics": met if isinstance(met, list) else [],
    }


async def propose_knowledge_from_schema(
    db: Any,
    *,
    organization: Any,
    data_source: Any,
    model: Any,
    focus: str = "both",
    llm_inference: Optional[Callable[[str], str]] = None,
) -> dict:
    """Introspect data_source schema, ask LLM for table descriptions + candidate
    metrics, UPSERT them as pending rows (reusing _propose_semantic_table /
    _propose_metric).

    focus in {'semantic','metrics','both'}. Returns {'semantics':[ids],
    'metrics':[ids]}. Gated by SEMANTIC_LAYER/METRICS_CATALOG inside the route,
    not here. NEVER raises — degrades to empty result on any failure.
    """
    out: dict = {"semantics": [], "metrics": []}
    try:
        org_id = str(getattr(organization, "id", None) or "")
        ds_id = str(getattr(data_source, "id", None) or "")
        if not org_id or not ds_id:
            return out

        focus = focus if focus in ("semantic", "metrics", "both") else "both"
        want_semantic = focus in ("semantic", "both")
        want_metric = focus in ("metrics", "both")

        # 1. Introspect schema (guarded). No tables -> nothing to propose.
        schema_text, existing_tables = _introspect_schema_text(data_source)
        if not schema_text or not existing_tables:
            return out

        # 2. One-shot LLM proposal. Default: same call shape the distiller uses.
        infer = llm_inference
        if infer is None:
            def infer(p: str) -> str:  # noqa: E306 - tiny lazy default
                from app.ai.llm.llm import LLM
                from app.dependencies import async_session_maker

                return LLM(model, usage_session_maker=async_session_maker).inference(p)

        prompt = build_schema_suggest_prompt(schema_text, focus)
        raw = (infer(prompt) or "").strip()
        proposal = _parse_suggest_proposal(raw)

        # 3a. Semantic tables (only for tables that EXIST in the schema).
        if want_semantic:
            for st in proposal.get("semantic_tables", [])[:8]:
                if not isinstance(st, dict):
                    continue
                table_name = _clean(st.get("table_name"))
                description = _clean(st.get("description"))
                if table_name not in existing_tables:
                    continue
                if table_name and len(description) >= _MIN_TEXT_LEN:
                    new_id = await _propose_semantic_table(
                        db,
                        org_id=org_id,
                        ds_id=ds_id,
                        table_name=table_name,
                        description=description,
                    )
                    if new_id:
                        out["semantics"].append(new_id)

        # 3b. Metrics.
        if want_metric:
            for m in proposal.get("metrics", [])[:6]:
                if not isinstance(m, dict):
                    continue
                name = _clean(m.get("name"))
                definition = _clean(m.get("definition"))
                sql_calc = _clean(m.get("sql_calc"))
                table_ref = _clean(m.get("table_ref"))
                if name and (len(definition) >= _MIN_TEXT_LEN or sql_calc):
                    new_id = await _propose_metric(
                        db,
                        org_id=org_id,
                        ds_id=ds_id,
                        name=name,
                        definition=definition,
                        sql_calc=sql_calc,
                        table_ref=table_ref,
                    )
                    if new_id:
                        out["metrics"].append(new_id)

        if out["semantics"] or out["metrics"]:
            await db.commit()
        return out
    except Exception as e:  # never raise to the caller
        logger.warning("knowledge_proposer propose_knowledge_from_schema failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"semantics": [], "metrics": []}


# ---------------------------------------------------------------------------
# AI column-meaning generator: fill the blank SemanticColumn.meaning rows that
# the GET /semantic seed leaves empty. Sibling of propose_knowledge_from_schema
# above — works off the ALREADY-SEEDED semantic tables (not raw schema), so the
# caller must have hit GET /semantic first. Approval-safe (status='pending', the
# approved-only injection keeps it out of the agent until reviewed). NEVER
# overwrites an approved or already-filled meaning. NEVER raises.
# ---------------------------------------------------------------------------


async def propose_column_meanings(
    db, *, organization, data_source, model, llm_inference=None
) -> dict:
    """Fill blank ``SemanticColumn.meaning`` rows for a data source via the LLM.

    Loads the org/ds semantic tables (with columns eager-loaded) in THIS async
    session, asks the model — per table — for a one-sentence meaning of each
    column whose meaning is still blank and whose status is not 'approved', and
    sets ``meaning``+``status='pending'`` so it lands in the Review gate. Returns
    {'columns': [<SemanticColumn.id>, ...]} of the columns that were filled.
    NEVER raises — degrades to {'columns': []} on any failure.
    """
    out: dict = {"columns": []}
    try:
        org_id = str(getattr(organization, "id", None) or "")
        ds_id = str(getattr(data_source, "id", None) or "")
        if not org_id or not ds_id:
            return out

        from app.models.semantic_table import SemanticTable, SemanticColumn  # noqa: F401
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        # 1. Load the already-seeded semantic tables + their columns in-session.
        #    No semantic tables yet -> nothing to fill (caller seeds via GET /semantic).
        result = await db.execute(
            select(SemanticTable)
            .where(
                SemanticTable.organization_id == org_id,
                SemanticTable.data_source_id == ds_id,
            )
            .options(selectinload(SemanticTable.columns))
        )
        sem_tables = result.scalars().all()
        if not sem_tables:
            return out

        # 2. Lazy default inference — same call shape the distiller/schema-suggest use.
        infer = llm_inference
        if infer is None:
            def infer(p: str) -> str:  # noqa: E306 - tiny lazy default
                from app.ai.llm.llm import LLM
                from app.dependencies import async_session_maker

                return LLM(model, usage_session_maker=async_session_maker).inference(p)

        changed = False
        for st in list(sem_tables)[:_MAX_SCHEMA_TABLES]:
            # 3. Collect the columns still needing a meaning (blank + not approved).
            blank_cols = [
                c
                for c in (getattr(st, "columns", None) or [])
                if not _clean(getattr(c, "meaning", None))
                and _clean(getattr(c, "status", None)) != "approved"
            ][:_MAX_SCHEMA_COLS]
            if not blank_cols:
                continue

            # 4. Build the per-table prompt: name, description, blank `col (type)` pairs.
            by_name = {}
            col_lines: list[str] = []
            for c in blank_cols:
                cname = _clean(getattr(c, "name", None))
                if not cname:
                    continue
                by_name[cname] = c
                ctype = _clean(getattr(c, "type", None))
                col_lines.append(f"{cname} ({ctype})" if ctype else cname)
            if not col_lines:
                continue

            prompt = build_column_meaning_prompt(
                _clean(getattr(st, "table_name", None)),
                _clean(getattr(st, "description", None)),
                col_lines,
            )

            # 5/6. One-shot LLM + tolerant parse -> {col: meaning} dict.
            raw = (infer(prompt) or "").strip()
            parsed = _parse_proposal(raw)
            if not isinstance(parsed, dict) or not parsed:
                continue

            # 7. Fill only the blank columns the model named, status -> 'pending'.
            for cname, col in by_name.items():
                meaning = _clean(parsed.get(cname))
                if len(meaning) < _MIN_TEXT_LEN:
                    continue
                col.meaning = meaning
                col.status = "pending"
                out["columns"].append(str(col.id))
                changed = True

        # 8. Commit once, only if we actually filled something.
        if changed:
            await db.commit()
        return out
    except Exception as e:  # never raise to the caller
        logger.warning("knowledge_proposer propose_column_meanings failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"columns": []}
