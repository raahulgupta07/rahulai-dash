"""L3 Codex Code Enrich — extract meaning from source DDL / profile_v2 (Wave1 P6).

For each active DataSourceTable in scope, we fetch the source definition (view DDL
for SQL-backend views, reconstructed CREATE TABLE for base tables, saved-query SQL
for file-based sources that carry SQL) and ask the LLM to extract:

  * grain   — the level at which each row represents one unit
  * formulas — derived/computed column expressions implied by the source code
  * population — which rows are included vs excluded (filters in the WHERE / HAVING)

Extracted facts are stored in DataSourceTable.metadata_json['pipeline_logic']:
    {
        "grain": "<one-sentence grain statement>",
        "formulas": [{"col": "<name>", "expr": "<SQL expression>"}],
        "population": "<one-sentence population description>",
        "source_sql_snippet": "<first 400 chars of the raw DDL/SQL>"
    }

For file-based sources (no DDL available), we fall back to profile_v2 column types
to infer a minimal grain statement without an LLM call.

Design rules (CLAUDE.md):
  * Gate: flags.CODE_ENRICH (HYBRID_CODE_ENRICH).  OFF → instant no-op.
  * LLM = same one-shot pattern as auto_queries (sync LLM.inference run in thread).
  * Approval-safe: writes only metadata_json (no knowledge-layer rows); no approval
    gate needed because pipeline_logic is an internal enrichment field, not surfaced
    in the Review tab.
  * Fail-soft: every stage is guarded; never raises into the caller.
  * Never touches create_data.py, inspect_data.py, or profile_v2.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)

# Maximum chars of DDL we send to the LLM (keeps token cost bounded).
_DDL_SNIPPET_MAX = 2000
# Minimum grain text length to consider a proposal useful.
_MIN_TEXT_LEN = 6


# ---------------------------------------------------------------------------
# DDL / SQL fetchers
# ---------------------------------------------------------------------------

def _safe_snippet(text: str, max_chars: int = _DDL_SNIPPET_MAX) -> str:
    """Truncate to max_chars safely."""
    if not text:
        return ""
    return text[:max_chars]


async def _fetch_view_ddl(client: Any, table_name: str) -> Optional[str]:
    """Try to fetch view definition via pg_get_viewdef (PostgreSQL).

    Uses execute_query which is the standard DataSourceClient interface.
    Non-PG connectors will error → return None (fail-soft).
    """
    try:
        sql = f"SELECT pg_get_viewdef('{table_name}'::regclass, true) AS def"
        df = await asyncio.to_thread(client.execute_query, sql)
        if df is not None and not df.empty:
            val = df.iloc[0, 0]
            if val and str(val).strip() not in ("", "None"):
                return str(val).strip()
    except Exception as e:
        logger.debug("code_enrich: pg_get_viewdef failed for %s: %s", table_name, e)
    return None


async def _fetch_table_ddl(client: Any, table_name: str) -> Optional[str]:
    """Try to reconstruct a minimal CREATE TABLE statement from information_schema."""
    try:
        sql = (
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' "
            "ORDER BY ordinal_position LIMIT 60"
        )
        df = await asyncio.to_thread(client.execute_query, sql)
        if df is not None and not df.empty:
            cols_def = ", ".join(
                f"{row['column_name']} {row['data_type']}"
                for _, row in df.iterrows()
                if row.get("column_name")
            )
            if cols_def:
                return f"CREATE TABLE {table_name} ({cols_def})"
    except Exception as e:
        logger.debug("code_enrich: info_schema DDL failed for %s: %s", table_name, e)
    return None


async def _get_source_sql(client: Any, table_name: str) -> Optional[str]:
    """Get best available source definition: view DDL → table DDL → None."""
    ddl = await _fetch_view_ddl(client, table_name)
    if ddl:
        return ddl
    ddl = await _fetch_table_ddl(client, table_name)
    return ddl


# ---------------------------------------------------------------------------
# LLM prompt + parsing
# ---------------------------------------------------------------------------

def _build_extraction_prompt(table_name: str, source_sql: str) -> str:
    snippet = _safe_snippet(source_sql, _DDL_SNIPPET_MAX)
    return (
        "You are a senior data engineer. Below is the source definition (DDL or view SQL) "
        f"for a table or view named `{table_name}`.\n\n"
        f"Source definition:\n```sql\n{snippet}\n```\n\n"
        "Extract the PIPELINE LOGIC in three parts:\n"
        "1. grain — one sentence describing what a single row represents "
        "(e.g. 'one transaction per customer per day').\n"
        "2. formulas — list of computed/derived columns with their expressions. "
        "Only include columns where the expression is non-trivially computed "
        "(e.g. CASE WHEN, arithmetic, function calls). Omit plain column renames.\n"
        "3. population — one sentence describing the included rows / any filters "
        "(WHERE clauses, exclusions).\n\n"
        "Return ONLY a single JSON object (no prose, no markdown fences):\n"
        '{"grain": "<one sentence>", '
        '"formulas": [{"col": "<col_name>", "expr": "<sql expression>"}], '
        '"population": "<one sentence>"}\n\n'
        "Rules:\n"
        "- Be concise. Each field ≤ 100 words.\n"
        "- If no derived columns exist, set formulas to [].\n"
        "- If no WHERE/HAVING filter exists, set population to 'All rows included'.\n"
        "- Output the JSON object ONLY."
    )


def _parse_extraction(text: str) -> Dict[str, Any]:
    """Best-effort parse model JSON. Returns {} on failure (never raises)."""
    if not text:
        return {}
    cleaned = text.strip()
    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(cleaned[start:end + 1], strict=False)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _infer_grain_from_profile(table_name: str, profile: Dict[str, Any]) -> str:
    """Derive a minimal grain statement from profile_v2 column roles (no LLM)."""
    identifiers = [c for c, info in profile.items()
                   if isinstance(info, dict) and info.get("role") == "IDENTIFIER"]
    temporals = [c for c, info in profile.items()
                 if isinstance(info, dict) and info.get("role") == "TEMPORAL"]

    parts: List[str] = []
    if identifiers:
        parts.append("per " + " + ".join(identifiers[:3]))
    if temporals:
        parts.append("per " + temporals[0])
    if not parts:
        return f"One row per record in {table_name}"
    return f"One row {' and '.join(parts)} in {table_name}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def enrich_table(
    db: AsyncSession,
    *,
    data_source: Any,
    tbl_row: Any,
    model: Any,
    llm_inference=None,
) -> bool:
    """Extract and store pipeline_logic for a single DataSourceTable.

    Parameters
    ----------
    db : AsyncSession
    data_source : DataSource ORM row (for get_client / type).
    tbl_row : DataSourceTable ORM row (mutated in place via metadata_json).
    model : LLM model object (from LLMService).
    llm_inference : Optional callable (str → str) for testing / injection.

    Returns True if pipeline_logic was written, False otherwise.
    Fail-soft — never raises.
    """
    if not flags.CODE_ENRICH:
        return False

    try:
        return await _enrich_table(db, data_source=data_source, tbl_row=tbl_row,
                                   model=model, llm_inference=llm_inference)
    except Exception as e:
        logger.warning("code_enrich.enrich_table failed for %s: %s",
                       getattr(tbl_row, "name", "?"), e)
        return False


async def _enrich_table(
    db: AsyncSession,
    *,
    data_source: Any,
    tbl_row: Any,
    model: Any,
    llm_inference=None,
) -> bool:
    table_name = getattr(tbl_row, "name", None) or ""
    if not table_name:
        return False

    meta = tbl_row.metadata_json
    if not isinstance(meta, dict):
        meta = {}

    # --- Try to get source SQL from the connector ---
    source_sql: Optional[str] = None
    try:
        client = data_source.get_client()
        source_sql = await _get_source_sql(client, table_name)
    except Exception as e:
        logger.debug("code_enrich: client/DDL fetch failed for %s: %s", table_name, e)

    # --- File-based fallback: derive grain from profile_v2 (no LLM needed) ---
    if not source_sql:
        profile = meta.get("profile_v2")
        if isinstance(profile, dict) and profile:
            grain = _infer_grain_from_profile(table_name, profile)
            _write_pipeline_logic(tbl_row, meta, grain=grain, formulas=[],
                                  population="All rows included",
                                  source_sql_snippet="")
            return True
        # No DDL and no profile → skip
        logger.debug("code_enrich: no DDL and no profile_v2 for %s — skip", table_name)
        return False

    # --- LLM extraction ---
    prompt = _build_extraction_prompt(table_name, source_sql)

    infer = llm_inference
    if infer is None:
        def infer(p: str) -> str:  # noqa: E306
            from app.ai.llm.llm import LLM
            from app.dependencies import async_session_maker

            return LLM(model, usage_session_maker=async_session_maker).inference(
                p, usage_scope="code_enrich"
            )

    raw: str = ""
    try:
        raw = await asyncio.to_thread(infer, prompt)
        raw = (raw or "").strip()
    except Exception as e:
        logger.warning("code_enrich: LLM call failed for %s: %s", table_name, e)
        return False

    extracted = _parse_extraction(raw)
    grain = str(extracted.get("grain") or "").strip()
    if not grain or len(grain) < _MIN_TEXT_LEN:
        logger.debug("code_enrich: empty/short grain from LLM for %s", table_name)
        return False

    formulas = extracted.get("formulas") or []
    if not isinstance(formulas, list):
        formulas = []
    population = str(extracted.get("population") or "All rows included").strip()

    _write_pipeline_logic(
        tbl_row, meta,
        grain=grain,
        formulas=formulas,
        population=population,
        source_sql_snippet=_safe_snippet(source_sql, 400),
    )
    return True


def _write_pipeline_logic(
    tbl_row: Any,
    meta: Dict[str, Any],
    *,
    grain: str,
    formulas: List[Dict[str, str]],
    population: str,
    source_sql_snippet: str,
) -> None:
    """Write pipeline_logic into tbl_row.metadata_json (mutates in-place)."""
    from sqlalchemy.orm.attributes import flag_modified

    meta = dict(meta)
    meta["pipeline_logic"] = {
        "grain": grain,
        "formulas": formulas,
        "population": population,
        "source_sql_snippet": source_sql_snippet,
    }
    tbl_row.metadata_json = meta
    try:
        flag_modified(tbl_row, "metadata_json")
    except Exception:
        pass  # flag_modified is best-effort when outside a session


async def enrich_source(
    db: AsyncSession,
    *,
    data_source: Any,
    organization: Any,
    model: Any,
    llm_inference=None,
) -> Dict[str, Any]:
    """Enrich all active tables in a data source.

    Returns {"enriched": <int>, "skipped": <int>}.  Fail-soft: per-table
    errors are caught and counted as skipped.  Commits once at the end.
    """
    if not flags.CODE_ENRICH:
        return {"enriched": 0, "skipped": 0}

    from sqlalchemy import select
    from app.models.datasource_table import DataSourceTable

    enriched = 0
    skipped = 0

    try:
        tbl_rows = list(
            (
                await db.execute(
                    select(DataSourceTable)
                    .where(DataSourceTable.datasource_id == str(data_source.id))
                    .where(DataSourceTable.is_active.is_(True))
                )
            ).scalars().all()
        )
    except Exception as e:
        logger.warning("code_enrich.enrich_source table fetch failed: %s", e)
        return {"enriched": 0, "skipped": 0}

    for tbl in tbl_rows:
        try:
            ok = await enrich_table(
                db, data_source=data_source, tbl_row=tbl,
                model=model, llm_inference=llm_inference,
            )
            if ok:
                enriched += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning("code_enrich: table %s error: %s", getattr(tbl, "name", "?"), e)
            skipped += 1

    try:
        await db.commit()
    except Exception as e:
        logger.warning("code_enrich.enrich_source commit failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    return {"enriched": enriched, "skipped": skipped}
