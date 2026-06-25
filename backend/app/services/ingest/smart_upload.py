"""Smart-upload helpers for the spreadsheet ingest path.

Pure / dependency-light functions shared by the two flag-gated ingest
improvements:

  * Task 5 (HYBRID_MERGE_SAME_SCHEMA) — content-hash dedup + same-schema append.
  * Task 6 (HYBRID_SMART_HEADER)      — xlsx header detection + glossary routing.

Everything here is defensive: on any error a helper returns a safe default
(``None`` / the input unchanged / ``False``) so the caller can always fall back
to today's behavior. NO DB access, NO raising into the ingest request path.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

# Provenance column stamped onto rows when same-schema files are merged into one
# table. Lowercase + leading underscore mirrors the loader's `_source_file`
# lineage convention so it sorts/reads as a system column.
SOURCE_LABEL_COL = "_source_label"

_GLOSSARY_NAME_RE = re.compile(r"(?i)(defin|glossary|dictionary|data\s*dict|field\s*list|lookup)")


# ---------------------------------------------------------------------------
# Task 5 — content hash + column-set normalization
# ---------------------------------------------------------------------------

def file_content_hash(path: str) -> str:
    """sha256 of file bytes (chunked). Returns "" on any failure."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.file_content_hash failed for %s", path, exc_info=True)
        return ""


def normalize_columns(columns: Iterable) -> frozenset:
    """Order-independent, lowercased+stripped column-set for schema matching.

    System/lineage columns (anything starting with ``_``) are excluded so a
    table that already carries `_source_label`/`_source_file` still matches a
    fresh upload of the same business columns.
    """
    out = set()
    try:
        for c in (columns if columns is not None else []):
            name = str(c).strip().lower()
            if not name or name.startswith("_"):
                continue
            out.add(name)
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.normalize_columns failed", exc_info=True)
        return frozenset()
    return frozenset(out)


def columns_match(a: Iterable, b: Iterable, *, min_jaccard: float = 1.0) -> bool:
    """True when two column-sets are 'the same schema'.

    Default ``min_jaccard=1.0`` == exact set equality (after normalization),
    which is the conservative same-template case the merge targets. A caller can
    relax it (e.g. 0.9) to tolerate a stray column, but exact is the default.
    """
    na, nb = normalize_columns(a), normalize_columns(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if min_jaccard >= 1.0:
        return False
    inter = len(na & nb)
    union = len(na | nb)
    return union > 0 and (inter / union) >= min_jaccard


def label_from_filename(filename: str) -> str:
    """Human-ish provenance label from a filename (stem, trimmed)."""
    try:
        stem = os.path.splitext(os.path.basename(filename or ""))[0].strip()
        return stem[:120] or (filename or "upload")
    except Exception:  # noqa: BLE001
        return filename or "upload"


# ---------------------------------------------------------------------------
# Task 6 — header detection + glossary detection (operate on a DataFrame)
# ---------------------------------------------------------------------------

def unnamed_fraction(columns: Iterable) -> float:
    """Fraction of columns that look like pandas placeholder headers.

    pandas names header-less columns ``Unnamed: 0``, ``Unnamed: 1`` … . A high
    fraction means read_excel didn't find a real header row.
    """
    cols = [str(c) for c in (columns if columns is not None else [])]
    if not cols:
        return 0.0
    bad = sum(
        1
        for c in cols
        if c.startswith("Unnamed:") or c.strip() == "" or c.lower() == "nan"
    )
    return bad / len(cols)


def _looks_like_header_row(values) -> float:
    """Score 0..1 — how header-like a row of raw cell values is.

    Header rows are mostly non-null, non-numeric, unique strings.
    """
    try:
        import pandas as pd  # local import keeps module import cheap

        vals = list(values)
        non_null = [
            v for v in vals
            if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != ""
        ]
        if len(non_null) < 2:
            return 0.0
        coverage = len(non_null) / max(len(vals), 1)
        strings = 0
        for v in non_null:
            s = str(v).strip()
            try:
                float(s.replace(",", ""))
            except (ValueError, TypeError):
                strings += 1
        string_frac = strings / len(non_null)
        uniq = len({str(v).strip().lower() for v in non_null})
        uniq_frac = uniq / len(non_null)
        return round(coverage * 0.3 + string_frac * 0.5 + uniq_frac * 0.2, 4)
    except Exception:  # noqa: BLE001
        return 0.0


def detect_header_row(raw_df, *, scan_rows: int = 10) -> Optional[int]:
    """Given a header=None DataFrame, return the best real-header row index.

    Scans the first ``scan_rows`` rows and returns the highest-scoring row whose
    score clears a confidence bar. Returns ``None`` if nothing looks like a
    header (caller keeps default behavior).
    """
    try:
        best_i, best_score = None, 0.0
        n = min(len(raw_df), scan_rows)
        for i in range(n):
            score = _looks_like_header_row(raw_df.iloc[i].tolist())
            if score > best_score:
                best_i, best_score = i, score
        if best_i is not None and best_score >= 0.6:
            return best_i
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.detect_header_row failed", exc_info=True)
    return None


def reread_with_detected_header(read_default, read_raw, *, sheet_label: str = ""):
    """Return a DataFrame with a corrected header when the default read produced
    too many ``Unnamed`` columns; otherwise return ``read_default`` unchanged.

    ``read_default`` : DataFrame from pandas' default header read.
    ``read_raw``      : DataFrame from the SAME source read with ``header=None``.

    The caller supplies both already-read frames so this helper does no IO.
    """
    try:
        frac = unnamed_fraction(read_default.columns)
        if frac <= 0.40:
            return read_default  # default header is fine
        hdr = detect_header_row(read_raw)
        if hdr is None:
            logger.info(
                "smart_header[%s]: %.0f%% Unnamed cols but no better header found; keeping default",
                sheet_label, frac * 100,
            )
            return read_default
        # Re-slice the raw frame: row `hdr` becomes the columns, rows below are data.
        new_cols = [str(v).strip() for v in read_raw.iloc[hdr].tolist()]
        body = read_raw.iloc[hdr + 1:].copy()
        body.columns = new_cols
        body = body.reset_index(drop=True)
        # Drop fully-empty trailing columns that the placeholder header created.
        body = body.dropna(axis=1, how="all")
        logger.info(
            "smart_header[%s]: corrected header (was %.0f%% Unnamed) -> picked row %d, cols=%s",
            sheet_label, frac * 100, hdr, list(body.columns)[:12],
        )
        return body
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.reread_with_detected_header failed", exc_info=True)
        return read_default


def looks_like_glossary(df, *, sheet_name: str = "", filename: str = "") -> bool:
    """Heuristic: is this sheet a field-definition glossary / data dictionary?

    Confident YES when EITHER:
      * the sheet/file name matches defin/glossary/dictionary/etc., OR
      * the table is narrow (2-3 usable columns) AND one column holds short
        unique field-name-like strings and another holds longer free-text
        descriptions.
    Conservative — returns False on doubt so normal tables stay queryable.
    """
    try:
        if _GLOSSARY_NAME_RE.search(str(sheet_name or "")) or _GLOSSARY_NAME_RE.search(str(filename or "")):
            return True

        import pandas as pd

        if df is None or df.empty:
            return False
        # Consider only non-empty columns.
        usable = [c for c in df.columns if df[c].notna().any()]
        if not (2 <= len(usable) <= 3):
            return False

        def _avg_len(series) -> float:
            vals = [str(v).strip() for v in series.dropna().tolist() if str(v).strip()]
            return (sum(len(v) for v in vals) / len(vals)) if vals else 0.0

        def _string_frac(series) -> float:
            vals = [v for v in series.dropna().tolist()]
            if not vals:
                return 0.0
            strings = 0
            for v in vals:
                s = str(v).strip()
                try:
                    float(s.replace(",", ""))
                except (ValueError, TypeError):
                    strings += 1
            return strings / len(vals)

        lens = {c: _avg_len(df[c]) for c in usable}
        strs = {c: _string_frac(df[c]) for c in usable}
        # need at least 2 mostly-text columns
        text_cols = [c for c in usable if strs[c] >= 0.8]
        if len(text_cols) < 2:
            return False
        shortest = min(text_cols, key=lambda c: lens[c])
        longest = max(text_cols, key=lambda c: lens[c])
        # name column short-ish, description column clearly longer free text
        return lens[shortest] <= 40 and lens[longest] >= 25 and lens[longest] >= lens[shortest] * 1.5
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.looks_like_glossary failed", exc_info=True)
        return False


def glossary_to_markdown(df, *, sheet_name: str = "") -> str:
    """Render a glossary DataFrame as a compact markdown body for KnowledgeDoc.

    Best-effort: assumes the first usable text column is the term and the next
    is the definition. Falls back to a CSV-ish dump on any trouble.
    """
    try:
        usable = [c for c in df.columns if df[c].notna().any()]
        if len(usable) >= 2:
            term_col, def_col = usable[0], usable[1]
            lines = [f"# Field definitions{(' — ' + str(sheet_name)) if sheet_name else ''}", ""]
            for _, row in df.iterrows():
                term = str(row.get(term_col, "")).strip()
                desc = str(row.get(def_col, "")).strip()
                if not term or term.lower() == "nan":
                    continue
                if desc and desc.lower() != "nan":
                    lines.append(f"- **{term}**: {desc}")
                else:
                    lines.append(f"- **{term}**")
            return "\n".join(lines)
        return df.to_csv(index=False)
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.glossary_to_markdown failed", exc_info=True)
        try:
            return df.to_csv(index=False)
        except Exception:  # noqa: BLE001
            return ""
