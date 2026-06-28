"""Universal Ingest Brain — pipeline orchestrator (ROADMAP F09).

Wires the 6 stages behind one entry point. Phase 0 = SKELETON: every stage is a
fail-soft stub so the module imports, the flag wiring is testable, and the
contract is exercised end-to-end with no behavior change. Real stage bodies land
in P1 (Excel+profile+preview), P2 (PDF/Word/image), P3 (unify→brain).

Hard rules (every phase):
- Gated by ``flags.INGEST_BRAIN``. OFF → ``run_pipeline`` returns ok=False with
  reason "disabled"; the caller falls back to today's ingest path. Byte-identical.
- NEVER raises into the request path. Any stage error → fail-soft, recorded in
  ``IngestResult.error``, pipeline returns what it has.
- STORE never commits silently — a PreviewDoc gates the commit (P1).
- Heavy stages (vision/camelot) run in a worker, not the HTTP request (P2).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.services.ingest_brain.contract import (
    SourceDoc, RawTable, ProseBlock, ColumnProfile, JoinCandidate,
    PreviewDoc, IngestResult,
)

logger = logging.getLogger(__name__)


# --- stage stubs (filled in P1/P2/P3) ---------------------------------------
def detect(path: str, filename: str) -> SourceDoc:
    """DETECT — sniff type + text-layer probe → route to a parser. [P1/P2]"""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    kind = {
        "xlsx": "spreadsheet", "xlsm": "spreadsheet", "xls": "spreadsheet",
        "csv": "spreadsheet", "tsv": "spreadsheet", "txt": "spreadsheet",
        "pdf": "text_pdf", "docx": "doc", "pptx": "doc",
        "png": "image", "jpg": "image", "jpeg": "image",
    }.get(ext, "unknown")
    return SourceDoc(path=path, filename=filename, ext=ext, kind=kind)


def extract(source: SourceDoc) -> tuple[List[RawTable], List[ProseBlock]]:
    """EXTRACT — source → clean RawTables + ProseBlocks.

    P1: spreadsheet via ``excel_extract`` (merged-cell fill + multi-table split +
    hierarchical-header flatten). On empty result, fall back to the existing
    ``ingest/excel_reader.read_excel`` so we never do worse than today.
    P2: PDF (pdfplumber/camelot), Word (docx), scanned/image (OpenRouter vision).
    """
    if source.kind != "spreadsheet" or source.ext in ("csv", "tsv", "txt"):
        return [], []   # CSV handled by existing path; PDF/Word land in P2
    try:
        from app.services.ingest_brain.excel_extract import extract_tables
        tables = extract_tables(source.path, filename=source.filename)
        return tables, []
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.extract failed")
        return [], []


def profile(tables: List[RawTable]) -> List[ColumnProfile]:
    """PROFILE — per column → ColumnProfile (dtype/unit/null%/role/PII). [P1]"""
    try:
        from app.services.ingest_brain.profiler import profile_tables
        return profile_tables(tables)
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.profile failed")
        return []


def understand(profiles: List[ColumnProfile], *, llm_inference=None) -> List[ColumnProfile]:
    """UNDERSTAND — LLM names each column meaning + synonyms (pending). [P3]"""
    return profiles


def unify(profiles: List[ColumnProfile], *, organization=None, db=None) -> List[JoinCandidate]:
    """UNIFY — fuzzy-match columns across all org sources → join candidates. [P3]"""
    return []


def build_preview(result: IngestResult) -> PreviewDoc:
    """Assemble the human-readable pre-commit summary (safety gate). [P1]"""
    n_tables = len(result.tables)
    n_cols = len(result.profiles)
    summary = (
        f"Read {n_tables} table(s) and profiled {n_cols} column(s) from "
        f"{result.source.filename if result.source else 'the file'}."
        if n_tables else "Nothing extracted yet (Phase 0 skeleton)."
    )
    return PreviewDoc(
        summary=summary,
        table_notes=[n for t in result.tables for n in t.notes],
        join_notes=[f"{j.left_ref} ↔ {j.right_ref} ({j.confidence:.0%})"
                    for j in result.join_candidates],
        auto_confirmable=(n_tables == 1 and not result.join_candidates),
    )


# --- orchestrator -----------------------------------------------------------
async def run_pipeline(path: str, filename: str, *, organization=None, db=None,
                       llm_inference=None) -> IngestResult:
    """Run DETECT→EXTRACT→PROFILE→UNDERSTAND→UNIFY and return a pre-commit result.

    STORE is intentionally separate (commit happens only after preview confirm).
    Returns ok=False, error="disabled" when the flag is OFF. NEVER raises.
    """
    from app.settings.hybrid_flags import flags

    if not flags.INGEST_BRAIN:
        return IngestResult(ok=False, error="disabled")

    result = IngestResult()
    try:
        result.source = detect(path, filename)
        result.tables, result.prose = extract(result.source)
        result.profiles = profile(result.tables)
        result.profiles = understand(result.profiles, llm_inference=llm_inference)
        result.join_candidates = unify(result.profiles, organization=organization, db=db)
        result.preview = build_preview(result)
        result.ok = True
    except Exception as exc:  # noqa: BLE001 — fail-soft per voice
        logger.exception("ingest_brain pipeline failed for %s", filename)
        result.ok = False
        result.error = str(exc)[:300]
    return result
