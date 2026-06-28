"""F09 PROFILE — RawTable → list[ColumnProfile] (Phase 1).

Pure-Python per-column profiling: dtype, unit, null%, cardinality, sample
values (PII-masked), PII flag, semantic role, synonyms. Deterministic, no LLM
(the LLM ``meaning`` is added later in the UNDERSTAND stage, P3). NEVER raises.

Mirrors the stats in ``routes/column_profile.py`` but works on in-memory rows
(pre-commit) instead of querying DuckDB, so the profile is ready for the preview
BEFORE anything is stored.
"""
from __future__ import annotations

import logging
import re
from typing import Any, List

from app.services.ingest_brain.contract import RawTable, ColumnProfile

logger = logging.getLogger(__name__)

_NULL = {"", "na", "n/a", "null", "none", "-", "?", "nan"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+()\-\d][\d\s()\-]{6,}$")
_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}|^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}")
_ID_NAME_RE = re.compile(r"(?i)(^|_)(id|code|sku|account|acct|barcode|upc|ean|ssn|iban)(_|$)")
_PII_NAME_RE = re.compile(r"(?i)(email|e-mail|phone|mobile|tel|name|first.?name|last.?name|address|ssn|dob|birth)")
_MEASURE_NAME_RE = re.compile(r"(?i)(amount|amt|revenue|sales|qty|quantity|count|total|price|cost|value|sum|units|margin|profit|spend)")
_DATE_NAME_RE = re.compile(r"(?i)(date|day|month|year|time|period|quarter|week)")
_UNIT_SYMBOL = [("%", "%"), ("₹", "₹"), ("$", "$"), ("€", "€"), ("£", "£"), ("kg", "kg"), ("km", "km")]

_SYNONYMS = {
    "revenue": ["sales", "turnover", "income"],
    "sales": ["revenue", "turnover"],
    "qty": ["quantity", "units", "volume"],
    "quantity": ["qty", "units", "volume"],
    "price": ["unit price", "rate", "asp"],
    "cost": ["expense", "spend"],
    "customer": ["client", "account", "buyer"],
    "product": ["item", "sku", "article"],
}


def _blank(v: Any) -> bool:
    return v is None or str(v).strip().lower() in _NULL


def _num(v: Any):
    try:
        return float(str(v).strip().replace(",", "").lstrip("₹$€£").rstrip("%"))
    except (ValueError, TypeError):
        return None


def _mask(v: Any, pii: bool) -> str:
    s = str(v).strip()
    if not pii:
        return s[:40]
    if _EMAIL_RE.match(s):
        u, d = s.split("@", 1)
        return (u[0] + "***@" + d)
    if len(s) <= 2:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 2) + s[-1]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _synonyms_for(norm_name: str) -> List[str]:
    for key, syns in _SYNONYMS.items():
        if key in norm_name:
            return syns
    return []


def profile_table(table: RawTable) -> List[ColumnProfile]:
    """Profile every column of one RawTable. NEVER raises."""
    profiles: List[ColumnProfile] = []
    try:
        ncols = len(table.header)
        n = len(table.rows)
        for c in range(ncols):
            name = table.header[c]
            col = [r[c] if c < len(r) else None for r in table.rows]
            non_null = [v for v in col if not _blank(v)]
            null_pct = round(100.0 * (n - len(non_null)) / n, 1) if n else 0.0
            distinct = len({str(v).strip().lower() for v in non_null})

            # dtype
            nums = [_num(v) for v in non_null]
            num_frac = (sum(1 for x in nums if x is not None) / len(non_null)) if non_null else 0.0
            date_frac = (sum(1 for v in non_null if _DATE_RE.match(str(v).strip())) / len(non_null)) if non_null else 0.0
            if date_frac > 0.6 or _DATE_NAME_RE.search(name):
                dtype = "date"
            elif num_frac > 0.8 and not _ID_NAME_RE.search(name):
                dtype = "float" if any((x is not None and x != int(x)) for x in nums if x is not None) else "int"
            else:
                dtype = "text"

            # PII
            pii = bool(_PII_NAME_RE.search(name)) or \
                (bool(non_null) and sum(1 for v in non_null[:50] if _EMAIL_RE.match(str(v).strip()) or _PHONE_RE.match(str(v).strip())) / min(len(non_null), 50) > 0.3)

            # role
            if _ID_NAME_RE.search(name) or (distinct == len(non_null) and distinct > 0 and dtype != "float" and _norm(name).endswith("id")):
                role = "id"
            elif dtype == "date":
                role = "date"
            elif dtype in ("int", "float") and (_MEASURE_NAME_RE.search(name) or num_frac > 0.9):
                role = "measure"
            else:
                role = "category"

            # unit
            unit = ""
            joined = " ".join(str(v) for v in non_null[:20])
            for sym, u in _UNIT_SYMBOL:
                if sym in joined or sym in name:
                    unit = u
                    break
            if not unit and "%" in name:
                unit = "%"

            samples = [_mask(v, pii) for v in non_null[:5]]
            profiles.append(ColumnProfile(
                name=name, normalized_name=_norm(name), dtype=dtype, unit=unit,
                null_pct=null_pct, cardinality=distinct, sample_values=samples,
                pii_flag=pii, semantic_role=role, synonyms=_synonyms_for(_norm(name)),
                source_ref={"source_file": table.source_file, "sheet": table.sheet, "col_index": c},
            ))
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.profile_table failed for %s", table.name)
    return profiles


def profile_tables(tables: List[RawTable]) -> List[ColumnProfile]:
    out: List[ColumnProfile] = []
    for t in tables:
        out.extend(profile_table(t))
    return out
