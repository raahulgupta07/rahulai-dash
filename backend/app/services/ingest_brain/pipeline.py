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
    try:
        from app.services.ingest_brain.detect import detect as _detect
        return _detect(path, filename)
    except Exception:  # noqa: BLE001 — fall back to extension-only routing
        ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
        kind = {
            "xlsx": "spreadsheet", "xlsm": "spreadsheet", "xls": "spreadsheet",
            "csv": "spreadsheet", "tsv": "spreadsheet", "txt": "spreadsheet",
            "pdf": "text_pdf", "docx": "doc", "pptx": "doc",
            "png": "image", "jpg": "image", "jpeg": "image",
        }.get(ext, "unknown")
        return SourceDoc(path=path, filename=filename, ext=ext, kind=kind)


def extract(source: SourceDoc, *, vision_infer=None) -> tuple[List[RawTable], List[ProseBlock]]:
    """EXTRACT — source → clean RawTables + ProseBlocks, routed by kind.

    P1 spreadsheet  → ``excel_extract`` (merged cells / multi-table / hier-header).
    P2 text_pdf     → ``pdf_extract.extract_pdf`` (pdfplumber + optional camelot).
       doc          → Word/PPT via docx/pptx.
       scanned/image→ ``vision_extract`` (OpenRouter vision; only no-text pages).
    CSV/TSV stays on the existing upload path. Every branch fail-soft → ([], []).
    """
    try:
        kind, ext = source.kind, source.ext
        if kind == "spreadsheet":
            if ext in ("csv", "tsv", "txt"):
                return [], []   # existing CSV path handles these
            from app.services.ingest_brain.excel_extract import extract_tables
            tbls = extract_tables(source.path, filename=source.filename)
            _, prose = _embedded_charts(source, vision_infer)        # P-F charts in xlsx
            return tbls, prose
        if kind == "text_pdf":
            from app.services.ingest_brain.pdf_extract import extract_pdf
            return extract_pdf(source.path, filename=source.filename)
        if kind == "doc":
            from app.services.ingest_brain.pdf_extract import extract_docx, extract_pptx
            if ext == "pptx":
                tbls, prose = extract_pptx(source.path, filename=source.filename)
            else:
                tbls, prose = extract_docx(source.path, filename=source.filename)
            tbls2, prose2 = _embedded_charts(source, vision_infer)   # P-F
            return tbls + tbls2, prose + prose2
        if kind == "legacy_excel":
            from app.services.ingest_brain.legacy_excel import extract_legacy_excel
            return extract_legacy_excel(source.path, ext, filename=source.filename), []
        if kind == "email":
            from app.services.ingest_brain.email_extract import (
                extract_html, extract_eml, extract_epub)
            if ext == "eml":
                return extract_eml(source.path, filename=source.filename)
            if ext == "epub":
                return extract_epub(source.path, filename=source.filename)
            return extract_html(source.path, filename=source.filename)
        if kind in ("scanned_pdf", "image"):
            from app.services.ingest_brain.vision_extract import extract_vision
            return extract_vision(source.path, ext, filename=source.filename,
                                  vision_infer=vision_infer, content_hash=source.content_hash)
        return [], []
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.extract failed")
        return [], []


def _embedded_charts(source: SourceDoc, vision_infer):
    """P-F: read images embedded in xlsx/pptx via vision → ProseBlocks. Fail-soft."""
    if vision_infer is None or source.ext not in ("xlsx", "xlsm", "pptx"):
        return [], []
    try:
        from app.services.ingest_brain.chart_extract import extract_embedded_charts
        return extract_embedded_charts(source.path, source.ext,
                                       filename=source.filename, vision_infer=vision_infer)
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain._embedded_charts failed")
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
    try:
        from app.services.ingest_brain.understand import understand_columns
        return understand_columns(profiles, llm_inference=llm_inference)
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.understand failed")
        return profiles


def unify(profiles: List[ColumnProfile], *, existing_columns=None) -> List[JoinCandidate]:
    """UNIFY — fuzzy-match this file's columns against the org's existing columns.

    ``existing_columns`` is the list of already-known org columns (the caller
    fetches them from the column_profiles table). Empty/None → no joins (the
    common first-file case). Pure + fail-soft. [P3]
    """
    try:
        if not existing_columns:
            return []
        from app.services.ingest_brain.unify import unify_columns
        return unify_columns(profiles, existing_columns)
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.unify failed")
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
                       llm_inference=None, vision_infer=None,
                       existing_columns=None) -> IngestResult:
    """Run DETECT→EXTRACT→PROFILE→UNDERSTAND→UNIFY and return a pre-commit result.

    STORE is intentionally separate (commit happens only after preview confirm).
    Returns ok=False, error="disabled" when the flag is OFF. NEVER raises.
    ``vision_infer(image_bytes, prompt)`` (optional) routes scanned/image pages
    through the org's OpenRouter vision model; absent → those land as a note.
    ``existing_columns`` (optional) = the org's already-known columns for the
    UNIFY cross-source join match (the route fetches them from column_profiles).
    """
    from app.settings.hybrid_flags import flags

    if not flags.INGEST_BRAIN:
        return IngestResult(ok=False, error="disabled")

    result = IngestResult()
    try:
        result.source = detect(path, filename)
        result.tables, result.prose = extract(result.source, vision_infer=vision_infer)
        result.profiles = profile(result.tables)
        result.profiles = understand(result.profiles, llm_inference=llm_inference)
        result.join_candidates = unify(result.profiles, existing_columns=existing_columns)
        result.preview = build_preview(result)
        result.ok = True
    except Exception as exc:  # noqa: BLE001 — fail-soft per voice
        logger.exception("ingest_brain pipeline failed for %s", filename)
        result.ok = False
        result.error = str(exc)[:300]
    return result
