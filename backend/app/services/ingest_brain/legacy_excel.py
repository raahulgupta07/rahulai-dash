"""F09 Ingest Brain, Phase E: legacy Excel readers.

Reads OLD Excel binary formats into clean :class:`RawTable` objects:

* ``.xls``  -> pandas with ``engine="xlrd"``
* ``.xlsb`` -> pandas with ``engine="pyxlsb"``

Unlike the modern ``.xlsx`` path, the ``xlrd`` and ``pyxlsb`` engines do NOT
expose merged-cell ranges, so we perform a simpler clean read (header sniff +
empty-row/col trim) rather than full merged-cell reconstruction. This is fine
for legacy formats; we annotate each table's notes accordingly.

Everything here is fully fail-soft: any error results in skipping the bad
sheet (or returning ``[]``). Nothing raised here should ever propagate.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services.ingest_brain.contract import RawTable

logger = logging.getLogger(__name__)

# Engine selection by lower-cased extension.
_ENGINE_BY_EXT: dict[str, str] = {
    "xls": "xlrd",
    "xlsb": "pyxlsb",
}

# How many leading rows to scan when sniffing the header row.
_HEADER_SCAN_ROWS = 15

# Fraction of non-null cells in a row that must look like text labels for the
# row to be considered the header row.
_HEADER_TEXT_RATIO = 0.60


def _excel_col_letter(index: int) -> str:
    """Convert a 0-based column index to an Excel column letter.

    0 -> "A", 25 -> "Z", 26 -> "AA", etc.
    """
    if index < 0:
        index = 0
    letters = ""
    n = index
    while True:
        n, rem = divmod(n, 26)
        letters = chr(ord("A") + rem) + letters
        if n == 0:
            break
        n -= 1
    return letters


def _slugify(name: str, *, max_len: int = 48) -> str:
    """Slugify a sheet name into ``[a-z0-9_]`` of at most ``max_len`` chars."""
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "sheet"
    return s[:max_len].strip("_") or "sheet"


def _is_text_label(value: Any) -> bool:
    """Return True if a cell value looks like a non-numeric text label."""
    if value is None:
        return False
    # NaN check without importing numpy/pandas at module scope.
    try:
        if value != value:  # noqa: PLR0124 - NaN is never equal to itself
            return False
    except Exception:
        pass
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    s = str(value).strip()
    if not s:
        return False
    # A pure number expressed as text is not a label.
    try:
        float(s.replace(",", ""))
        return False
    except (ValueError, TypeError):
        return True


def _find_header_row(df: Any) -> int:
    """Find the index of the header row within the first rows of ``df``.

    The header row is the first row where >= 60% of its non-null cells are
    non-numeric string labels. Returns 0 if no obvious header is found.
    """
    try:
        n_scan = min(_HEADER_SCAN_ROWS, len(df))
    except Exception:
        return 0
    for i in range(n_scan):
        try:
            row = list(df.iloc[i])
        except Exception:
            continue
        non_null = [v for v in row if v is not None and (v == v)]  # noqa: PLR0124
        if not non_null:
            continue
        labels = sum(1 for v in non_null if _is_text_label(v))
        if labels / len(non_null) >= _HEADER_TEXT_RATIO:
            return i
    return 0


def _dedup_headers(names: list[str]) -> list[str]:
    """Fill blank header names (col_A, col_B...) and de-duplicate."""
    out: list[str] = []
    seen: dict[str, int] = {}
    for idx, raw in enumerate(names):
        name = str(raw).strip() if raw is not None and (raw == raw) else ""  # noqa: PLR0124
        if not name or name.lower().startswith("unnamed"):
            name = f"col_{_excel_col_letter(idx)}"
        base = name
        if name in seen:
            seen[name] += 1
            name = f"{base}_{seen[base]}"
        else:
            seen[name] = 0
        out.append(name)
    return out


def _none_if_nan(value: Any) -> Any:
    """Return None for NaN/NaT-like values, otherwise the value unchanged."""
    if value is None:
        return None
    try:
        if value != value:  # noqa: PLR0124 - NaN
            return None
    except Exception:
        pass
    return value


def extract_legacy_excel(
    path: str, ext: str, *, filename: str = ""
) -> list[RawTable]:
    """Extract clean tables from a legacy Excel file (``.xls`` / ``.xlsb``).

    Args:
        path: Filesystem path to the workbook.
        ext: File extension without the dot (``"xls"`` or ``"xlsb"``).
        filename: Optional original filename for provenance.

    Returns:
        A list of :class:`RawTable`, one per usable sheet. Always returns a
        list; never raises.
    """
    norm_ext = (ext or "").lower().lstrip(".")
    engine = _ENGINE_BY_EXT.get(norm_ext)
    if engine is None:
        logger.warning("extract_legacy_excel: unsupported ext %r", ext)
        return []

    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover - pandas missing
        logger.warning("extract_legacy_excel: pandas unavailable: %s", exc)
        return []

    try:
        sheets = pd.read_excel(
            path, sheet_name=None, header=None, engine=engine
        )
    except Exception as exc:
        logger.warning(
            "extract_legacy_excel: failed to read %s (engine=%s): %s",
            path,
            engine,
            exc,
        )
        return []

    src = filename or path or ""
    engine_note = "read via xlrd" if engine == "xlrd" else "read via pyxlsb"
    notes = [
        engine_note,
        "merged-cell handling not available for legacy format",
    ]

    tables: list[RawTable] = []
    for sheet_name, df in (sheets or {}).items():
        try:
            table = _sheet_to_table(pd, df, sheet_name, src, list(notes))
        except Exception as exc:
            logger.warning(
                "extract_legacy_excel: skipping sheet %r: %s",
                sheet_name,
                exc,
            )
            continue
        if table is not None:
            tables.append(table)

    return tables


def _sheet_to_table(
    pd: Any,
    df: Any,
    sheet_name: Any,
    src: str,
    notes: list[str],
) -> RawTable | None:
    """Convert a single raw sheet DataFrame into a RawTable (or None)."""
    if df is None or getattr(df, "empty", True):
        return None

    # Drop fully-empty rows/cols up front so the header sniff is reliable.
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return None
    df = df.reset_index(drop=True)

    header_idx = _find_header_row(df)
    header_values = list(df.iloc[header_idx])
    header = _dedup_headers(header_values)

    body = df.iloc[header_idx + 1 :].reset_index(drop=True)
    body = body.dropna(how="all").dropna(axis=1, how="all")
    if len(body) < 2:
        return None

    # Re-align header length to whatever columns survived the trim.
    ncols = body.shape[1]
    if len(header) < ncols:
        header = header + [
            f"col_{_excel_col_letter(i)}" for i in range(len(header), ncols)
        ]
    elif len(header) > ncols:
        header = header[:ncols]
    header = _dedup_headers(header)

    rows: list[list] = []
    for _, raw_row in body.iterrows():
        rows.append([_none_if_nan(v) for v in raw_row.tolist()])

    if len(rows) < 2:
        return None

    return RawTable(
        name=_slugify(str(sheet_name)),
        header=header,
        rows=rows,
        source_file=src,
        sheet=str(sheet_name),
        region_bbox=None,
        notes=notes,
    )
