"""Deep Profiler v2 — per-column role catalog.

Wave1 P1: classify each column as DIMENSION / STATE / MEASURE / IDENTIFIER /
TEMPORAL, collect top-3 values + frequency for categorical cols, and detect
near-duplicate value variants (e.g. "USA"/"U.S."/"United States").  Results
are persisted into DataSourceTable.metadata_json['profile_v2'].

Gate: flags.PROFILE_V2.  When OFF this module is a pure no-op — no DB reads,
no prompt changes.  Fail-soft on every risky step.
"""
from __future__ import annotations

import logging
import re
import string
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------
DIMENSION  = "DIMENSION"    # low-to-mid cardinality categorical (groupable)
STATE      = "STATE"        # boolean / small fixed-set status enum
MEASURE    = "MEASURE"      # numeric (aggregatable)
IDENTIFIER = "IDENTIFIER"   # high-cardinality surrogate / natural key
TEMPORAL   = "TEMPORAL"     # date / time / timestamp

# ---------------------------------------------------------------------------
# Internal helpers (reuse patterns from profiler.py)
# ---------------------------------------------------------------------------
_NUMERIC_TYPES  = ("int", "float", "numeric", "decimal", "double", "real",
                   "serial", "money", "bigint", "smallint")
_TEMPORAL_TYPES = ("date", "time", "timestamp", "interval")
_BOOL_TYPES     = ("bool", "boolean")

_TOP_VALUES_LIMIT = 10   # fetch up to this from DB; keep top-3 in output
_STATE_MAX_DISTINCT = 20 # ≤ N distinct → candidate for STATE
_DIM_MAX_DISTINCT   = 500


def _is_numeric(dtype: str) -> bool:
    d = (dtype or "").lower()
    return any(t in d for t in _NUMERIC_TYPES) and "timestamp" not in d


def _is_temporal(dtype: str) -> bool:
    d = (dtype or "").lower()
    return any(t in d for t in _TEMPORAL_TYPES)


def _is_bool(dtype: str) -> bool:
    d = (dtype or "").lower()
    return any(t in d for t in _BOOL_TYPES)


def _classify_role(col_name: str, dtype: str, distinct: int,
                   row_count: int) -> str:
    """Heuristic role classifier."""
    nl = (col_name or "").lower()
    # TEMPORAL — dtype wins
    if _is_temporal(dtype):
        return TEMPORAL
    # IDENTIFIER — _id suffix OR high-cardinality
    if nl.endswith("_id") or nl in ("id", "uuid", "guid", "pk"):
        return IDENTIFIER
    if row_count and distinct >= max(1, row_count * 0.90):
        return IDENTIFIER
    # BOOL — treat as STATE
    if _is_bool(dtype):
        return STATE
    # NUMERIC — MEASURE
    if _is_numeric(dtype):
        return MEASURE
    # Small fixed set → STATE (status / flag columns)
    if 0 < distinct <= _STATE_MAX_DISTINCT:
        name_hints = any(h in nl for h in ("status", "state", "flag", "type",
                                           "category", "tier", "level", "phase",
                                           "stage", "is_", "has_", "enabled",
                                           "active", "valid", "approved"))
        if name_hints or distinct <= 6:
            return STATE
    # Default → DIMENSION
    return DIMENSION


# ---------------------------------------------------------------------------
# Near-duplicate variant detector
# ---------------------------------------------------------------------------
_PUNCT_RE = re.compile(r"[" + re.escape(string.punctuation) + r"\s]+")


def _normalize(v: str) -> str:
    """casefold + strip + collapse punctuation/whitespace."""
    return _PUNCT_RE.sub("", str(v).casefold().strip())


def _detect_variants(values: List[str]) -> Optional[str]:
    """Return a warning string if any two values normalize to the same token."""
    seen: Dict[str, str] = {}
    collisions: List[str] = []
    for v in values:
        key = _normalize(v)
        if not key:
            continue
        if key in seen and seen[key] != v:
            pair = f'"{seen[key]}" / "{v}"'
            if pair not in collisions:
                collisions.append(pair)
        else:
            seen[key] = v
    if not collisions:
        return None
    sample = "; ".join(collisions[:3])
    return f"near-duplicate variants detected: {sample}"


# ---------------------------------------------------------------------------
# Value normalization → canonical (flags.VALUE_NORMALIZE)
# ---------------------------------------------------------------------------
# Detection only: cluster near-duplicate spellings of one real category, pick a
# canonical winner, and emit a value→canonical map + agent guardrail.  Never
# rewrites the stored data.
_NORM_MAX_DISTINCT = 200   # only normalize LOW-cardinality dimensions
_MAX_CLUSTERS      = 10    # cap clusters reported per column
_MAX_MAP_ENTRIES   = 50    # cap total variant→canonical entries per column
_INSTR_PAIR_CAP    = 8     # how many explicit pairs to spell out in the instruction


def _pick_canonical(members: List[tuple]) -> str:
    """members = [(value, count), ...].  Canonical = most frequent spelling,
    tie-break by longest, then lexically smallest."""
    return sorted(
        members,
        key=lambda m: (-int(m[1] or 0), -len(str(m[0])), str(m[0])),
    )[0][0]


def _cluster_variants(top_values: List[Dict[str, Any]], distinct: int):
    """Cluster near-duplicate spellings inside a low-cardinality dimension.

    Returns ``(canonical_map, summary, instruction)`` where ``canonical_map`` is
    ``{variant_value: canonical_value}`` for the NON-canonical members of every
    cluster of >=2 spellings, or ``({}, "", "")`` when nothing collides.

    Conservative: bails on high-cardinality columns; only clusters values whose
    normalized form TRULY collides; caps clusters + map size.  Detection only —
    never mutates stored data.
    """
    try:
        # High-cardinality columns are not safe to auto-merge.
        if distinct and distinct > _NORM_MAX_DISTINCT:
            return {}, "", ""

        # Group (value, count) by normalized key.
        groups: Dict[str, List[tuple]] = {}
        for tv in top_values or []:
            if not isinstance(tv, dict):
                continue
            val = tv.get("value")
            if val is None:
                continue
            sval = str(val)
            key = _normalize(sval)
            if not key:
                continue
            try:
                cnt = int(tv.get("count")) if tv.get("count") is not None else 0
            except Exception:
                cnt = 0
            groups.setdefault(key, []).append((sval, cnt))

        canonical_map: Dict[str, str] = {}
        summaries: List[str] = []
        clusters_used = 0

        for _key, members in groups.items():
            distinct_spellings = {m[0] for m in members}
            if len(distinct_spellings) < 2:          # need >=2 real spellings
                continue
            if clusters_used >= _MAX_CLUSTERS:
                break
            canonical = _pick_canonical(members)
            variants = [v for v in sorted(distinct_spellings) if v != canonical]
            if not variants:
                continue
            for v in variants:
                if len(canonical_map) >= _MAX_MAP_ENTRIES:
                    break
                canonical_map[v] = canonical
            clusters_used += 1
            shown = variants[0]
            more = f" (+{len(variants) - 1} more)" if len(variants) > 1 else ""
            summaries.append(
                f"'{shown}'{more} → '{canonical}' "
                f"({len(distinct_spellings)} spellings merged)"
            )

        if not canonical_map:
            return {}, "", ""

        summary = "; ".join(summaries[:_MAX_CLUSTERS])
        pairs = "; ".join(
            f"'{v}'→'{c}'" for v, c in list(canonical_map.items())[:_INSTR_PAIR_CAP]
        )
        instruction = (
            "spelling variants — treat as the same category; map "
            f"{pairs}. Normalize (CASE/REPLACE, or GROUP BY a normalized "
            "expression) BEFORE aggregating, else per-category totals scatter."
        )
        return canonical_map, summary, instruction
    except Exception as e:
        logger.debug("profile_v2 _cluster_variants: %s", e)
        return {}, "", ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def profile_table_v2(table, df_sample=None) -> dict:
    """Classify columns, collect top-3 values, detect variants.

    Parameters
    ----------
    table : DataSourceTable
        ORM row.  Must have .name, .datasource (with .id), and .metadata_json.
    df_sample : pandas.DataFrame or None
        If provided, stats are derived from the sample instead of hitting DB
        (useful for tests / in-process callers that already have a df).
        When None, the function connects to the analytics DB directly.

    Returns
    -------
    dict  — empty {} when flags.PROFILE_V2 is OFF.
    """
    from app.settings.hybrid_flags import flags
    if not flags.PROFILE_V2:
        return {}

    try:
        return _profile_table_v2_impl(table, df_sample)
    except Exception as e:
        logger.warning("profile_table_v2: unexpected error for table %s: %s",
                       getattr(table, "name", "?"), e)
        return {}


def _profile_table_v2_impl(table, df_sample) -> dict:
    tbl_name = getattr(table, "name", None)
    if not tbl_name:
        return {}

    # Attempt to get column stats either from the df_sample or from DB.
    col_stats: List[Dict[str, Any]] = []

    if df_sample is not None:
        col_stats = _stats_from_df(df_sample)
    else:
        col_stats = _stats_from_db(tbl_name)

    if not col_stats:
        return {}

    result: Dict[str, Any] = {}
    table_canonical_map: Dict[str, Dict[str, str]] = {}

    # Value-normalization is a separate, additive sub-feature gated by its own
    # flag; PROFILE_V2 behavior is byte-identical when VALUE_NORMALIZE is OFF.
    try:
        from app.settings.hybrid_flags import flags as _flags
        _value_normalize = bool(_flags.VALUE_NORMALIZE)
    except Exception:
        _value_normalize = False

    for cs in col_stats:
        col_name = cs.get("name", "")
        dtype    = cs.get("dtype", "")
        distinct = int(cs.get("distinct", 0))
        row_count = int(cs.get("row_count", 0))

        role = _classify_role(col_name, dtype, distinct, row_count)

        entry: Dict[str, Any] = {"role": role}

        # Top-3 values + frequency for DIMENSION and STATE cols
        if role in (DIMENSION, STATE) and cs.get("top_values"):
            top = cs["top_values"][:3]
            entry["top_values"] = [
                {"value": tv.get("value"), "count": tv.get("count")}
                for tv in top
            ]
            # Variant detection on all fetched top values (up to _TOP_VALUES_LIMIT)
            raw_vals = [str(tv.get("value", "")) for tv in cs["top_values"]
                        if tv.get("value") is not None]
            warn = _detect_variants(raw_vals)
            if warn:
                entry["variants_warning"] = warn

            # VALUE_NORMALIZE: cluster spellings → canonical + map + guardrail.
            if _value_normalize:
                cmap, csummary, cinstr = _cluster_variants(
                    cs["top_values"], distinct
                )
                if cmap:
                    entry["value_canonical_map"] = cmap
                    entry["value_canonical_summary"] = csummary
                    entry["normalize_instruction"] = cinstr
                    # Route an actionable note through the EXISTING warning
                    # channel so it surfaces to the agent with no other change;
                    # the full instruction rides on normalize_instruction.
                    entry["variants_warning"] = csummary
                    table_canonical_map[col_name] = cmap
        else:
            entry["top_values"] = []

        result[col_name] = entry

    # Persist into table.metadata_json['profile_v2'] (+ value_canonical_map).
    _persist(table, result, table_canonical_map)

    return result


def _stats_from_df(df) -> List[Dict[str, Any]]:
    """Derive column stats from a pandas DataFrame sample."""
    stats: List[Dict[str, Any]] = []
    try:
        n = len(df)
        for col in df.columns:
            ser = df[col]
            dtype = str(ser.dtype)
            distinct = int(ser.nunique(dropna=True))
            top_values: List[Dict[str, Any]] = []
            try:
                vc = ser.dropna().value_counts().head(_TOP_VALUES_LIMIT)
                for val, cnt in vc.items():
                    top_values.append({"value": _jsonable(val), "count": int(cnt)})
            except Exception:
                pass
            stats.append({
                "name": col,
                "dtype": dtype,
                "distinct": distinct,
                "row_count": n,
                "top_values": top_values,
            })
    except Exception as e:
        logger.debug("profile_v2 _stats_from_df: %s", e)
    return stats


def _stats_from_db(tbl_name: str) -> List[Dict[str, Any]]:
    """Pull column stats from the analytics DB (write engine, safe for pgbouncer)."""
    try:
        from sqlalchemy import text
        from app.services.autotrain.profiler import _safe_ident, _jsonable, _is_numeric

        tbl = _safe_ident(tbl_name)
        schema = "staging"
        sch = _safe_ident(schema)
    except Exception as e:
        logger.warning("profile_v2 _stats_from_db: bad identifiers: %s", e)
        return []

    try:
        from app.ai.code_execution.analytics_engine import get_analytics_write_engine
        engine = get_analytics_write_engine()
    except Exception as e:
        logger.warning("profile_v2 _stats_from_db: cannot get engine: %s", e)
        return []

    qname = f'"{sch}"."{tbl}"'
    stats: List[Dict[str, Any]] = []
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            row_count = int(conn.execute(
                text(f"SELECT COUNT(*) FROM {qname}")
            ).scalar() or 0)

            cols = conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"
                ),
                {"s": schema, "t": tbl_name},
            ).fetchall()

            for col_name, dtype in cols:
                try:
                    from app.services.autotrain.profiler import _safe_ident as _si, _jsonable as _jv
                    c = f'"{_si(col_name)}"'
                    distinct = int(conn.execute(
                        text(f"SELECT COUNT(DISTINCT {c}) FROM {qname}")
                    ).scalar() or 0)
                    top_values: List[Dict[str, Any]] = []
                    if distinct <= _DIM_MAX_DISTINCT:
                        tv_rows = conn.execute(
                            text(
                                f"SELECT {c} AS v, COUNT(*) AS n FROM {qname} "
                                f"WHERE {c} IS NOT NULL GROUP BY {c} "
                                f"ORDER BY n DESC LIMIT {_TOP_VALUES_LIMIT}"
                            )
                        ).fetchall()
                        top_values = [{"value": _jv(v), "count": int(n)}
                                      for v, n in tv_rows]
                    stats.append({
                        "name": col_name,
                        "dtype": str(dtype),
                        "distinct": distinct,
                        "row_count": row_count,
                        "top_values": top_values,
                    })
                except Exception as ce:
                    logger.debug("profile_v2 col %s: %s", col_name, ce)
                    stats.append({"name": col_name, "dtype": str(dtype),
                                  "distinct": 0, "row_count": row_count,
                                  "top_values": []})
    except Exception as e:
        logger.warning("profile_v2 _stats_from_db(%s): %s", tbl_name, e)
    return stats


def _jsonable(v):
    """Safe JSON scalar conversion (mirrors profiler.py)."""
    try:
        if v is None:
            return None
        if isinstance(v, (int, str, bool, float)):
            return v
        from datetime import datetime
        if isinstance(v, datetime):
            return v.isoformat()
        try:
            from decimal import Decimal
            if isinstance(v, Decimal):
                return float(v)
        except ImportError:
            pass
        return str(v)
    except Exception:
        return str(v)


def _persist(table, result: dict, value_canonical_map: dict = None) -> None:
    """Merge result into table.metadata_json['profile_v2'] in place.

    When ``value_canonical_map`` is non-empty (VALUE_NORMALIZE ON) it is also
    written to ``metadata_json['value_canonical_map']`` = ``{column: {variant:
    canonical}}`` so SQL builders can normalize before GROUP BY.  When empty the
    key is left untouched → PROFILE_V2-only behavior is unchanged.

    Does NOT open a DB session or commit — caller owns the session lifecycle.
    We mutate table.metadata_json so SQLAlchemy's change-tracking sees the
    update when the caller commits.
    """
    try:
        from sqlalchemy.orm.attributes import flag_modified
        meta = table.metadata_json if isinstance(table.metadata_json, dict) else {}
        meta = dict(meta)
        meta["profile_v2"] = result
        if value_canonical_map:
            meta["value_canonical_map"] = value_canonical_map
        table.metadata_json = meta
        try:
            flag_modified(table, "metadata_json")
        except Exception:
            pass
    except Exception as e:
        logger.debug("profile_v2 _persist: %s", e)


# ---------------------------------------------------------------------------
# Prompt block builder
# ---------------------------------------------------------------------------

def build_profile_v2_block(table) -> str:
    """Render a compact ~80-char/col summary of the profile_v2 for the planner.

    Returns "" when flags.PROFILE_V2 is OFF or no profile data is available.

    Sections: DIMENSIONS / STATES / MEASURES / IDENTIFIERS / TEMPORAL
    Each column line: "  col_name [dtype?] — top: v1(n), v2, v3  ⚠ variant warn"
    Capped at ~80 chars/line (long lines are truncated with …).
    """
    from app.settings.hybrid_flags import flags
    if not flags.PROFILE_V2:
        return ""

    try:
        meta = getattr(table, "metadata_json", None)
        if not isinstance(meta, dict):
            return ""
        profile = meta.get("profile_v2")
        if not isinstance(profile, dict) or not profile:
            return ""

        tbl_name = getattr(table, "name", "unknown")

        # Bucket by role
        buckets: Dict[str, List[tuple]] = {
            DIMENSION:  [],
            STATE:      [],
            MEASURE:    [],
            IDENTIFIER: [],
            TEMPORAL:   [],
        }
        for col, info in profile.items():
            if not isinstance(info, dict):
                continue
            role = info.get("role", DIMENSION)
            if role not in buckets:
                role = DIMENSION
            buckets[role].append((col, info))

        lines = [f"<profile_v2 table={tbl_name}>"]

        _ROLE_LABEL = {
            DIMENSION:  "DIMENSIONS",
            STATE:      "STATES",
            MEASURE:    "MEASURES",
            IDENTIFIER: "IDENTIFIERS",
            TEMPORAL:   "TEMPORAL",
        }

        for role, label in _ROLE_LABEL.items():
            cols = buckets[role]
            if not cols:
                continue
            lines.append(f"  [{label}]")
            for col, info in cols:
                tv = info.get("top_values") or []
                warn = info.get("variants_warning", "")

                top_str = ""
                if tv:
                    parts = []
                    for item in tv[:3]:
                        val = item.get("value")
                        cnt = item.get("count")
                        if val is not None:
                            s = str(val)
                            if cnt is not None:
                                s += f"({cnt})"
                            parts.append(s)
                    if parts:
                        top_str = "top: " + ", ".join(parts)

                line = f"    {col}"
                if top_str:
                    line += f" — {top_str}"
                if warn:
                    # keep warning concise
                    short_warn = warn[:60] + "…" if len(warn) > 60 else warn
                    line += f"  ⚠ {short_warn}"

                # Truncate to ~120 chars
                if len(line) > 120:
                    line = line[:119] + "…"
                lines.append(line)

        lines.append("</profile_v2>")
        return "\n".join(lines)

    except Exception as e:
        logger.debug("build_profile_v2_block: %s", e)
        return ""
