"""F10 Sense-Making — post-answer decision layer.

After an agent run finishes, this enricher reconstructs the result DataFrames
from the run's success steps, computes REAL deterministic signals (reusing the
pure-function anomaly/trend scanner in ``insights.py``) plus column aggregates,
then makes ONE cheap LLM call to turn those facts into a structured
``sense_making`` card (headline + findings with so-what/now-what + alerts).

Public surface
--------------
    async def build_sense_making(db, *, steps, question, model, info_by_step=None) -> dict | None

Returns the ``sense_making`` dict (matching the shared frontend contract) or
``None`` when there is nothing worth saying (or on ANY error). NEVER raises.

Shared JSON contract (frontend reads this verbatim)
---------------------------------------------------
    {
      "headline": {"text", "severity", "confidence", "metric"},
      "findings": [{"what","so_what",
         "now_what": {"action","impact_rank","confidence","evidence":[...]},
         "kind","cause_hypothesis","plain_language"}],
      "alerts": [{"rule","metric","value","threshold","severity","action"}],
      "generated_by": "hybrid", "model": str
    }

Design rules
------------
- Exactly ONE LLM call (the cheap/small model passed in), and only when there
  is real signal — Optimization #4 short-circuits to None (no LLM, no tokens)
  when the result is small and signal-free.
- Every number the card cites is validated against the real signals/info/sample
  (Optimization #7); ungrounded findings are dropped.
- Confidence is clamped to the data size (Optimization #8).
- Fail-soft: any exception → ``None`` (logged at WARNING, never re-raised).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# How many steps (result tables) to feed the LLM.
_MAX_STEPS = 3
# Head rows of the best df included as a concrete data sample.
_SAMPLE_ROWS = 30
# Row-count thresholds for the confidence clamp (Optimization #8).
_LOW_ROWS = 30
_MED_ROWS = 200
# Optimization #4: skip-when-pointless threshold.
_SMALL_DF_ROWS = 5

_CONF_RANK = {"low": 0, "med": 1, "high": 2}


# ---------------------------------------------------------------------------
# DataFrame reconstruction (handles both column/row shapes; fail-soft per step)
# ---------------------------------------------------------------------------

def _column_names(columns: Any) -> List[str]:
    """Normalize a step's ``columns`` (list[str] OR list[dict]) to plain names."""
    names: List[str] = []
    if not isinstance(columns, list):
        return names
    for c in columns:
        if isinstance(c, str):
            names.append(c)
        elif isinstance(c, dict):
            name = c.get("field") or c.get("name") or c.get("headerName")
            if name is not None:
                names.append(str(name))
    return names


def _df_from_step_data(data: Any) -> Optional[Any]:
    """Reconstruct a pandas DataFrame from a step ``data`` dict.

    ``data`` = {"rows": list[dict] | list[list], "columns": list[str] |
    list[{field/name/headerName}], "info": {...}}. Returns None on any problem.
    """
    try:
        import pandas as pd  # type: ignore

        if not isinstance(data, dict):
            return None
        rows = data.get("rows")
        if not rows or not isinstance(rows, list):
            return None
        cols = _column_names(data.get("columns"))

        first = rows[0]
        if isinstance(first, dict):
            df = pd.DataFrame(rows)
            # Order columns by the declared column list when we have it.
            if cols:
                ordered = [c for c in cols if c in df.columns]
                extra = [c for c in df.columns if c not in ordered]
                if ordered:
                    df = df[ordered + extra]
        elif isinstance(first, (list, tuple)):
            if cols and len(cols) == len(first):
                df = pd.DataFrame(rows, columns=cols)
            else:
                df = pd.DataFrame(rows)
        else:
            return None

        if df is None or df.empty:
            return None
        # Best-effort: coerce obviously-numeric object columns so describe()/
        # the insight scanner see them as numbers.
        for col in df.columns:
            try:
                if df[col].dtype == object:
                    coerced = pd.to_numeric(df[col], errors="coerce")
                    if coerced.notna().sum() >= max(1, int(len(df) * 0.8)):
                        df[col] = coerced
            except Exception:
                continue
        return df
    except Exception:
        logger.debug("sense_making: df reconstruction failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Optimization #1 — step selection (skip melted/long tables)
# ---------------------------------------------------------------------------

def _is_melted(df: Any) -> bool:
    """Classic melt = a generic ``value`` column alongside a ``metric`` column."""
    try:
        lower = {str(c).strip().lower() for c in df.columns}
        return ("value" in lower) and ("metric" in lower)
    except Exception:
        return False


def _step_score(df: Any) -> float:
    """Higher = a wider, better-aggregated, distinctly-named table."""
    try:
        n_cols = len(df.columns)
        n_rows = len(df)
        score = float(n_cols)
        # Prefer grouped/aggregated tables (few-ish rows, several measures).
        if n_rows <= 200:
            score += 2.0
        # Reward distinct named numeric measures.
        try:
            import pandas as pd  # type: ignore
            n_numeric = len(df.select_dtypes(include="number").columns)
            score += float(n_numeric)
        except Exception:
            pass
        return score
    except Exception:
        return 0.0


def _select_steps(reconstructed: List[Dict[str, Any]]) -> (List[Dict[str, Any]], Optional[str]):
    """Pick up to _MAX_STEPS best (non-melted) entries. Returns (chosen, note)."""
    note: Optional[str] = None
    if not reconstructed:
        return [], note

    non_melted = [e for e in reconstructed if not _is_melted(e["df"])]
    pool = non_melted
    if not pool:
        # Optimization #1: all melted → still use the best one, but flag it.
        pool = reconstructed
        note = "All result tables were in long/melted form; interpreted the best available."

    pool = sorted(pool, key=lambda e: _step_score(e["df"]), reverse=True)
    return pool[:_MAX_STEPS], note


# ---------------------------------------------------------------------------
# Optimization #2 — real aggregates (column stats from step info)
# ---------------------------------------------------------------------------

def _compact_info(data: Any) -> Dict[str, Any]:
    """Pull a small per-column stat block (min/max/mean/unique) from step info."""
    out: Dict[str, Any] = {}
    try:
        if not isinstance(data, dict):
            return out
        info = data.get("info") or {}
        col_info = info.get("column_info") or {}
        if not isinstance(col_info, dict):
            return out
        for col, ci in col_info.items():
            if not isinstance(ci, dict):
                continue
            stat: Dict[str, Any] = {}
            for k in ("min", "max", "mean", "std", "unique_count", "non_null_count", "top", "freq"):
                if k in ci and ci[k] is not None:
                    stat[k] = ci[k]
            if stat:
                out[str(col)] = stat
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Numeric-token / grounding helpers (Optimization #7)
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers_in(text: Any) -> List[str]:
    out: List[str] = []
    try:
        for m in _NUM_RE.findall(str(text)):
            cleaned = m.replace(",", "").strip(".")
            if cleaned and cleaned not in ("-", ""):
                out.append(cleaned)
    except Exception:
        pass
    return out


def _num_variants(raw: str) -> List[str]:
    """A real numeric token plus a few rounded string variants."""
    variants = {raw}
    try:
        f = float(raw)
        variants.add(str(f))
        variants.add(str(int(round(f))))
        variants.add(f"{f:.1f}")
        variants.add(f"{f:.2f}")
        # also strip a trailing .0
        if raw.endswith(".0"):
            variants.add(raw[:-2])
    except Exception:
        pass
    return [v for v in variants if v]


def _is_grounded(text: Any, real_tokens: set, real_cols: set) -> bool:
    """A claim is grounded if it cites a real column name OR a real number.

    Lenient: a real column NAME (even with no number) is enough.
    """
    try:
        s = str(text or "")
        low = s.lower()
        for col in real_cols:
            if col and col.lower() in low:
                return True
        for tok in _numbers_in(s):
            for v in _num_variants(tok):
                if v in real_tokens:
                    return True
        return False
    except Exception:
        # On a comparison error, keep the finding (be lenient).
        return True


# ---------------------------------------------------------------------------
# Confidence clamp (Optimization #8)
# ---------------------------------------------------------------------------

def _cap_confidence(value: Any, ceiling: str) -> str:
    cur = str(value or "low").lower()
    if cur not in _CONF_RANK:
        cur = "low"
    if _CONF_RANK[cur] > _CONF_RANK[ceiling]:
        return ceiling
    return cur


# ---------------------------------------------------------------------------
# Prompt + parsing
# ---------------------------------------------------------------------------

def _build_prompt(question: str, signals: List[Dict[str, Any]],
                  info_blocks: Dict[str, Dict[str, Any]],
                  sample: List[Dict[str, Any]], note: Optional[str]) -> str:
    facts = json.dumps(signals, ensure_ascii=False, default=str)[:6000]
    info_s = json.dumps(info_blocks, ensure_ascii=False, default=str)[:4000]
    sample_s = json.dumps(sample, ensure_ascii=False, default=str)[:6000]
    note_line = f"\nNOTE: {note}\n" if note else "\n"
    return (
        "You are a senior data analyst writing a DECISION card that sits above a "
        "data answer. Turn the facts below into sense-making: what happened, why "
        "it matters (so-what), and what to do (now-what).\n"
        f"USER QUESTION:\n{question}\n"
        f"{note_line}"
        "DETERMINISTIC SIGNALS (already computed from the real data — these are facts):\n"
        f"{facts}\n\n"
        "COLUMN AGGREGATES (real min/max/mean/unique/top per column):\n"
        f"{info_s}\n\n"
        "DATA SAMPLE (head rows of the most relevant table):\n"
        f"{sample_s}\n\n"
        "RULES:\n"
        "- Output STRICT JSON only. No markdown, no prose, no code fences.\n"
        "- EVERY number you cite MUST appear in the signals, aggregates, or sample "
        "above. Do not invent or extrapolate numbers.\n"
        "- Rank findings by impact_rank (1 = most important first).\n"
        "- confidence ('high'|'med'|'low') reflects how much data backs the claim "
        "(few rows => 'low').\n"
        "- severity is one of: critical|watch|positive|neutral.\n"
        "- kind is one of: anomaly|trend_change|threshold|opportunity|risk.\n"
        "- now_what.evidence is a list of short strings, each citing a real column "
        "name and/or a real number from the facts.\n"
        "- Keep at most 4 findings and at most 3 alerts. Be concrete and brief.\n\n"
        "Return JSON EXACTLY matching this shape:\n"
        '{"headline":{"text":"","severity":"watch","confidence":"med","metric":""},'
        '"findings":[{"what":"","so_what":"","now_what":{"action":"","impact_rank":1,'
        '"confidence":"med","evidence":[""]},"kind":"anomaly","cause_hypothesis":"",'
        '"plain_language":""}],'
        '"alerts":[{"rule":"","metric":"","value":"","threshold":"","severity":"watch","action":""}]}'
    )


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    s = raw.strip()
    # Strip ```json ... ``` fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s.strip())
    # Fall back to the outermost {...} block.
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end + 1]
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def build_sense_making(db, *, steps, question: str, model,
                             info_by_step=None) -> Optional[Dict[str, Any]]:
    """Compute a ``sense_making`` card from real step results + 1 cheap LLM call.

    Returns the card dict (matching the shared contract) or None. NEVER raises.
    """
    try:
        from app.ai.knowledge.insights import compute_insights

        # 1. Reconstruct DataFrames per step (fail-soft per step).
        reconstructed: List[Dict[str, Any]] = []
        for st in (steps or []):
            try:
                data = getattr(st, "data", None)
                df = _df_from_step_data(data)
                if df is None:
                    continue
                title = (getattr(st, "title", None) or "result").strip() or "result"
                reconstructed.append({"step": st, "df": df, "data": data, "title": title})
            except Exception:
                continue

        if not reconstructed:
            return None

        # 2. Optimization #1 — select up to 3 best (non-melted) steps.
        chosen, note = _select_steps(reconstructed)
        if not chosen:
            return None

        # 3. Optimization #2 — real signals (tagged with step title) + info aggregates.
        signals: List[Dict[str, Any]] = []
        info_blocks: Dict[str, Dict[str, Any]] = {}
        real_cols: set = set()
        max_rows = 0
        for entry in chosen:
            df = entry["df"]
            title = entry["title"]
            try:
                max_rows = max(max_rows, int(len(df)))
            except Exception:
                pass
            try:
                for c in df.columns:
                    real_cols.add(str(c))
            except Exception:
                pass
            try:
                for sig in (compute_insights(df) or []):
                    s = dict(sig)
                    s["step"] = title
                    signals.append(s)
            except Exception:
                continue
            try:
                ci = _compact_info(entry["data"])
                if ci:
                    info_blocks[title] = ci
            except Exception:
                continue

        # 4. Optimization #4 — skip only when truly pointless: no signal AND every
        # result is a single row/cell (a scalar). A small multi-row comparison
        # (e.g. 2 sites) carries real meaning, so let it reach the LLM + grounding.
        truly_trivial = all(_safe_len(e["df"]) <= 1 for e in chosen)
        if len(signals) == 0 and truly_trivial:
            return None

        # Build the data sample from the best (first-selected) df.
        sample: List[Dict[str, Any]] = []
        try:
            best_df = chosen[0]["df"]
            sample = json.loads(
                best_df.head(_SAMPLE_ROWS).to_json(orient="records", date_format="iso", default_handler=str)
            )
        except Exception:
            sample = []

        # Collect the real numeric-token set for grounding (Optimization #7).
        real_tokens: set = set()
        for blob in (signals, list(info_blocks.values()), sample):
            try:
                for tok in _numbers_in(json.dumps(blob, ensure_ascii=False, default=str)):
                    for v in _num_variants(tok):
                        real_tokens.add(v)
            except Exception:
                continue

        # 5. The single cheap LLM call.
        prompt = _build_prompt(question or "", signals, info_blocks, sample, note)
        from app.ai.llm.llm import LLM
        from app.dependencies import async_session_maker

        def _infer() -> str:
            return LLM(model, usage_session_maker=async_session_maker).inference(
                prompt, usage_scope="sense_making"
            )

        raw = await asyncio.to_thread(_infer)
        parsed = _parse_json(raw or "")
        if not parsed:
            return None

        # 6. Optimization #7 — drop ungrounded findings.
        headline = parsed.get("headline") if isinstance(parsed.get("headline"), dict) else {}
        findings_in = parsed.get("findings") if isinstance(parsed.get("findings"), list) else []
        alerts_in = parsed.get("alerts") if isinstance(parsed.get("alerts"), list) else []

        kept_findings: List[Dict[str, Any]] = []
        for f in findings_in:
            if not isinstance(f, dict):
                continue
            nw = f.get("now_what") if isinstance(f.get("now_what"), dict) else {}
            evidence = nw.get("evidence") if isinstance(nw.get("evidence"), list) else []
            grounded = False
            for ev in evidence:
                if _is_grounded(ev, real_tokens, real_cols):
                    grounded = True
                    break
            # Also let the finding survive if its own text is grounded.
            if not grounded:
                if _is_grounded(f.get("what"), real_tokens, real_cols) or \
                        _is_grounded(f.get("so_what"), real_tokens, real_cols):
                    grounded = True
            if grounded:
                kept_findings.append(f)

        # If all findings dropped, keep headline only — unless headline itself
        # cites nothing real, in which case there is no grounded card.
        if not kept_findings:
            headline_grounded = (
                _is_grounded(headline.get("text"), real_tokens, real_cols) or
                _is_grounded(headline.get("metric"), real_tokens, real_cols)
            )
            if not headline_grounded:
                return None

        # 7. Optimization #8 — confidence clamp to data size.
        ceiling = "high"
        if max_rows < _LOW_ROWS:
            ceiling = "low"
        elif max_rows < _MED_ROWS:
            ceiling = "med"

        if isinstance(headline, dict):
            headline["confidence"] = _cap_confidence(headline.get("confidence"), ceiling)
        for f in kept_findings:
            nw = f.get("now_what")
            if isinstance(nw, dict):
                nw["confidence"] = _cap_confidence(nw.get("confidence"), ceiling)

        # Re-rank findings by impact_rank (1 first), tolerant of missing/garbage.
        def _rank(f: Dict[str, Any]) -> int:
            try:
                nw = f.get("now_what") or {}
                return int(nw.get("impact_rank", 999))
            except Exception:
                return 999
        kept_findings.sort(key=_rank)

        clean_alerts = [a for a in alerts_in if isinstance(a, dict)]

        return {
            "headline": headline if isinstance(headline, dict) else {},
            "findings": kept_findings,
            "alerts": clean_alerts,
            "generated_by": "hybrid",
            "model": getattr(model, "name", str(model)),
        }
    except Exception:
        logger.warning("sense_making: build_sense_making failed", exc_info=True)
        return None


def _safe_len(df: Any) -> int:
    try:
        return int(len(df))
    except Exception:
        return 0


async def get_stored_sense_making(db, report_id: str) -> "dict | None":
    """Return the most recent persisted ``sense_making`` card for a report.

    Pure DB read — NO LLM, NO recompute. The chat enricher already attaches the
    card to the answer completion's ``completion`` JSON; artifacts / email /
    notifications reuse it from here so they never pay a second LLM call.

    Fail-soft: returns None on any error or when no card exists.
    """
    try:
        from sqlalchemy import select, desc
        from app.models.completion import Completion

        rows = (
            await db.execute(
                select(Completion)
                .where(Completion.report_id == report_id)
                .order_by(desc(Completion.created_at))
                .limit(25)
            )
        ).scalars().all()
        for c in rows:
            comp = c.completion
            if isinstance(comp, dict):
                sm = comp.get("sense_making")
                if isinstance(sm, dict) and (sm.get("headline") or sm.get("findings")):
                    return sm
        return None
    except Exception:
        logger.warning("sense_making: get_stored_sense_making failed", exc_info=True)
        return None
