"""Universal Ingest Brain — frozen stage contracts (ROADMAP F09).

These dataclasses are the ONLY interface the 6 pipeline stages share. Freeze
them like ``services/report_delivery/contract.py`` so a stage (Excel extractor,
PDF extractor, profiler, unifier) can be swapped without touching the others.
Pure data — NO logic, NO DB, NO imports beyond stdlib/typing.

Pipeline:
    DETECT → EXTRACT → PROFILE → UNDERSTAND → UNIFY → STORE+LEARN

Stage I/O:
    detect(file)            -> SourceDoc
    extract(SourceDoc)      -> list[RawTable] + list[ProseBlock]
    profile(RawTable)       -> list[ColumnProfile]
    understand(profiles)    -> enriches ColumnProfile.meaning/synonyms (LLM)
    unify(profiles, org)    -> list[JoinCandidate]
    store(IngestResult)     -> commits to the existing model chain (review-gated)

Reuse (already in the repo, do NOT rebuild):
    services/ingest/excel_reader.py  — header detect, null-clean, numeric safety,
                                       LLM rescue. P1 EXTENDS it (merged cells,
                                       multi-table split, hierarchical headers).
    routes/column_profile.py         — DuckDB column profiler (role/dtype/stats).
    brain/knowledge_proposer.py      — column meanings + semantic proposals.
    brain/brain_graph.py             — cross-source join edges (pending).

Everything is fail-soft: a stage that cannot do its job returns empty / passes
input through, so an unknown file degrades to today's behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --- DETECT -----------------------------------------------------------------
@dataclass
class SourceDoc:
    """One uploaded file after type + text-layer probing (stage DETECT)."""
    path: str
    filename: str
    ext: str                       # normalized lowercase, no dot: xlsx/csv/pdf/docx/png...
    kind: str                      # spreadsheet | text_pdf | scanned_pdf | doc | image | unknown
    has_text_layer: bool = True    # False → route to vision (no GPU; OpenRouter)
    content_hash: str = ""         # reuse file_content_hash → dedup + vision cache key
    size_bytes: int = 0
    notes: List[str] = field(default_factory=list)


# --- EXTRACT ----------------------------------------------------------------
@dataclass
class RawTable:
    """A single clean rectangular table pulled from a source (stage EXTRACT).

    A messy Excel sheet may yield N RawTables (region detection). Merged cells
    are already forward-filled and multi-row headers already flattened here, so
    downstream stages see a clean grid.
    """
    name: str                              # proposed table name
    header: List[str]                      # flattened, unique column names
    rows: List[List[Any]]                  # data rows (header excluded)
    source_file: str = ""
    sheet: Optional[str] = None
    region_bbox: Optional[str] = None      # "A3:F210" provenance of the region
    notes: List[str] = field(default_factory=list)   # "merged col Region filled", "dropped 2 blank rows"


@dataclass
class ProseBlock:
    """Free text extracted from PDF/Word (stage EXTRACT) → KnowledgeDoc later."""
    title: str
    body: str
    source_file: str = ""
    page: Optional[int] = None


# --- PROFILE / UNDERSTAND ----------------------------------------------------
@dataclass
class ColumnProfile:
    """Durable per-column understanding (stage PROFILE, enriched by UNDERSTAND).

    This is what makes a dataset reusable anytime: the agent and the user both
    see meaning/unit/role/links, not a bare column name. Persisted to the NEW
    ``column_profile`` table in P1.
    """
    name: str
    normalized_name: str = ""
    dtype: str = "text"                     # int | float | date | bool | text
    unit: str = ""                          # ₹ / % / kg / count (heuristic + LLM)
    null_pct: float = 0.0
    cardinality: int = 0
    sample_values: List[str] = field(default_factory=list)   # ≤5, PII-masked
    pii_flag: bool = False                  # name/email/phone/id → privacy aware
    semantic_role: str = "category"         # id | date | measure | category
    synonyms: List[str] = field(default_factory=list)        # revenue≈sales≈turnover
    meaning: str = ""                       # LLM-written, UNDERSTAND stage (pending)
    maps_to: str = ""                       # canonical brain entity (cross-source, UNIFY)
    source_ref: Dict[str, Any] = field(default_factory=dict) # {source_file, sheet, col_index}


# --- UNIFY ------------------------------------------------------------------
@dataclass
class JoinCandidate:
    """A proposed cross-source join (stage UNIFY) → brain_graph edge (pending)."""
    left_ref: str                           # "salesA.cust_id"
    right_ref: str                          # "crmC.customer"
    confidence: float = 0.0                 # 0..1, shown in preview
    reason: str = ""                        # "name+value overlap"


# --- result + preview -------------------------------------------------------
@dataclass
class PreviewDoc:
    """Human-readable summary shown BEFORE commit (non-negotiable safety gate).

    Stage STORE never writes silently. The UI renders this and the user confirms
    or corrects (header row / table split) first.
    """
    summary: str = ""                       # "Read 3 tables from sheet Q2…"
    table_notes: List[str] = field(default_factory=list)
    join_notes: List[str] = field(default_factory=list)
    auto_confirmable: bool = False          # clean single-table high-confidence → may skip


@dataclass
class IngestResult:
    """Everything the pipeline produced for one file, pre-commit."""
    source: Optional[SourceDoc] = None
    tables: List[RawTable] = field(default_factory=list)
    profiles: List[ColumnProfile] = field(default_factory=list)
    prose: List[ProseBlock] = field(default_factory=list)
    join_candidates: List[JoinCandidate] = field(default_factory=list)
    preview: PreviewDoc = field(default_factory=PreviewDoc)
    ok: bool = True
    error: str = ""
