# Universal Ingest Brain — Design

> ROADMAP **F09** (supersedes F06). One pipeline: drop in **any** file → understand its structure
> deeply → clean it → register it into **one org-level brain** so the agent knows every dataset and
> how they relate. GPU-free (OpenRouter-only). Default OFF behind `HYBRID_INGEST_BRAIN`.
>
> Companion: `ROADMAP.md` §2/§3/§9, `docs/CODEBASE_MAP.md` (ingest path), `CLAUDE.md` (landmines).
> Status: **BUILT P0–P3 on branch `feature/ingest-brain`** (flag `HYBRID_INGEST_BRAIN` OFF, NOT merged,
> NOT baked). Last updated 2026-06-29.
>
> **Built (branch only, additive, sidecar package `services/ingest_brain/`):**
> - P0 — flag (3-place, OFF) + frozen `contract.py` + `pipeline.py` orchestrator (fail-soft, returns
>   "disabled" when flag off → ingest byte-identical to today).
> - P1 — `excel_extract.py` (merged-cell forward-fill, N-tables-per-sheet split, 2-row hierarchical
>   header flatten, banner skip, sparse-row flag) + `profiler.py` (dtype/unit/null%/cardinality/PII-mask/
>   role/synonyms) + `column_profiles` table (mig `colprofile1` off head `sessumm1`, PG-guarded) +
>   `routes/ingest_brain.py` (`POST /api/ingest-brain/preview` + `/profiles/{ds}`, decoupled from
>   `create_data_source_from_file`) + FE `components/ingest/Preview.vue` (`<IngestPreview>` safety gate).
> - P2 — `detect.py` (text-layer probe) + `pdf_extract.py` (pdfplumber/camelot-optional, docx, pptx) +
>   `vision_extract.py` (scanned/image → PyMuPDF PNG → OpenRouter vision callable, hash-cached, page cap).
> - P3 — `unify.py` (pure cross-source column matcher: name-sim + value-overlap, id/category only) +
>   `understand.py` (cheap-LLM column meanings/synonyms, grounded, callable-decoupled). Preview surfaces
>   join candidates from the org's existing `column_profiles`.
>
> **Self-tested pure-Python (no docker):** messy workbook → merged-fill span=3, 2 tables/sheet split,
> `2024 · Q1` hierarchical header, email PII masked; Word table+prose; PDF text-layer+prose;
> `cust_id ↔ crmC.customer` join @0.87. **NOT yet run inside the live stack** (route + migration + FE need
> a deploy to verify end-to-end) and the vision callable + ingest-time brain-graph/knowledge-proposer
> write (STORE auto-learn) are plumbed but not live-wired — that's the remaining P3 tail before any bake.

---

## 0. Goal in one line

> A user uploads any messy Excel / CSV / PDF / Word / image. The platform reads it the way a careful
> analyst would — finds the real tables, fixes merged cells and shifted headers, profiles every
> column, learns what each column *means*, and files it into a single shared brain. From then on the
> agent already knows that data and how it joins to everything else the user ever uploaded.

Two hard requirements from the user, kept front-and-center:
1. **No GPU.** We are OpenRouter-only. Nothing may require a local GPU.
2. **One brain.** All datasets unify into a single org brain (Compas-style), not per-file islands.
3. **Deep column + sheet understanding.** Merged cells, row-merges, multi-row headers, N-tables-per-
   sheet — all detected and captured properly, never silently mangled.

---

## 1. Where it plugs in (no new architecture)

Enters as the **DataSource ingest path** — one of the "two doors" from ROADMAP §0 (DataSource type OR
agent tool). It wraps the *existing* upload flow, it does not replace it.

Today (verified in code):
```
POST /api/data_sources/from-file
  → routes/data_source_from_file.py::create_data_source_from_file()
  → SpreadsheetClient (pandas.read_excel/read_csv → DuckDB in-memory)
  → smart_upload (header detect, glossary route, same-schema merge)   [flag HYBRID_SMART_HEADER]
  → Connection(type='spreadsheet') → ConnectionTable → DataSourceTable
```
Gaps: Excel/CSV only; header detection shallow; no merged-cell/multi-table handling; no per-column
profile; no PDF/Word/image; brain learns only on 👎, never on ingest.

F09 inserts a **6-stage pipeline** between "file received" and "DataSource created", and adds an
**ingest-time brain trigger** at the end. Storage stays the existing model chain — no new store.

---

## 2. The single brain

One org-level brain every dataset feeds. Reuses tables/services that already exist; adds `ColumnProfile`.

```
        ┌──────────────────────  ONE BRAIN (per org)  ──────────────────────┐
        │ SemanticTable     what each table is (exists — knowledge layer)    │
        │ ColumnProfile     every column: meaning/unit/PII/role  (NEW table) │
        │ MetricDefinition  candidate metrics (exists)                       │
        │ brain_graph (AGE) cross-source joins + entity links (exists)       │
        │ KnowledgeDoc      prose/glossary from PDF/Word (exists)            │
        └────────────────────────────────────────────────────────────────────┘
            ▲          ▲          ▲          ▲          ▲
         Excel A    PDF B     Word C    image D    CSV E
        every ingest REGISTERS into the same brain (status=pending → review gate)
```

- **Cross-source intelligence:** brain learns `salesA.cust_id ↔ crmC.customer` even though they came
  from different files in different formats → proposes the join as an AGE graph edge.
- **Agent already knows:** at query time the planner reads the brain (existing context builders) →
  no per-question schema re-scan; it knows what data exists, what each column means, how to join.
- **Review-gated:** every brain write lands `status=pending`. Nothing auto-trusted. User approves in
  the existing Knowledge UI. Matches current distiller/knowledge_proposer discipline.
- **New trigger only:** today `knowledge_proposer` + `distiller` fire on thumbs-down. F09 adds an
  ingest-time fire point. Same proposers, new caller. No change to the approval model.

---

## 3. GPU-free parser matrix

Hard rule: **born-digital → CPU library** (fast, free, deterministic). **Only scanned/image → vision
LLM via OpenRouter** (cloud, no local GPU). Docling rejected as default (its table/layout model is
GPU-bound); allowed only as an optional CPU-fallback flag.

| Input | Primary parser | Tables | Compute | Notes |
|---|---|---|---|---|
| `.xlsx/.xlsm/.xls` | `sheetsense` port + openpyxl | native | pure CPU | region/merge/header — §5 |
| `.csv/.tsv/.txt` | pandas (existing) | native | pure CPU | sniff delimiter |
| text PDF | `pdfplumber` | `camelot` (lattice+stream) | pure CPU | born-digital only in v1 |
| scanned PDF / `.png/.jpg` | **OpenRouter vision model** | vision → JSON rows | cloud, no GPU | only when no text layer |
| `.docx` | `python-docx` | table iter | pure CPU | prose → KnowledgeDoc |
| `.pptx` | `python-pptx` | table iter | pure CPU | optional |
| email/html/epub | `unstructured` (CPU mode) | partial | CPU | optional catch-all |

**Routing decision (stage DETECT):**
- has extractable text layer? → CPU lib.
- image / scanned / zero text → vision LLM, **page-by-page**, cache by content hash (reuse existing
  `file_content_hash`). Never send a born-digital page to the LLM (cost + nondeterminism).

Dependencies added (all CPU, all pip): `pdfplumber`, `camelot-py[base]`, `python-docx`,
`python-pptx`. (`openpyxl`, `pandas`, `duckdb` already present.) `unstructured` optional.
camelot needs `ghostscript` — already? verify; poppler/soffice already in image (report_delivery).

---

## 4. Pipeline — 6 stages

Behind `create_data_source_from_file`, gated by `HYBRID_INGEST_BRAIN`. Heavy stages run in a worker
(not the HTTP request) and stream progress.

```
1 DETECT      sniff type + text-layer probe → route to parser
2 EXTRACT     Excel→sheetsense(regions+merge+header)  PDF→pdfplumber/camelot
              scanned→OpenRouter vision  Word→docx  → list[RawTable] + list[ProseBlock]
3 PROFILE     per column → ColumnProfile (dtype, unit, null%, cardinality, samples, PII, role)
4 UNDERSTAND  LLM (OpenRouter) names each table + column meaning + synonyms; born-digital only
5 UNIFY       fuzzy-match columns across ALL existing org sources → candidate join edges
6 STORE+LEARN tables→ConnectionTable (queryable via DuckDB); prose→KnowledgeDoc;
              register SemanticTable + ColumnProfile + MetricDefinition + AGE edges → brain (pending)
```

**Stage contracts (frozen interfaces so stages stay swappable — mirror report_delivery `contract.py`):**
```
RawTable    = { name, header: list[str], rows: list[list], source_file, sheet, region_bbox, notes }
ColumnProfile = { name, normalized_name, dtype, unit, null_pct, cardinality,
                  sample_values[≤5], pii_flag, semantic_role, synonyms[], maps_to, source_ref }
ProseBlock  = { title, body, source_file, page }
IngestResult= { tables: list[RawTable], profiles: list[ColumnProfile],
                prose: list[ProseBlock], join_candidates: list[Edge], preview: PreviewDoc }
```

**Preview gate (between stage 5 and 6 — non-negotiable):** stage 6 NEVER commits silently. It returns
a `PreviewDoc`:
> "Read **3 tables** from sheet *Q2*. Header = row 3 (skipped a title + blank row). Merged column
> *Region* filled down into 14 cells. Dropped 2 fully-blank rows. Detected join: `cust_id` →
> existing `crm.customer`. **Looks right?**"

User confirms (or corrects header row / table split) → then commit. Auto-confirm allowed only for
clean single-table sheets with high confidence (configurable threshold).

---

## 5. Deep sheet + column capture (the core ask)

The user was explicit: every sheet's columns understood, row-merges and merged cells captured
properly. This is the `sheetsense` port plus a profiling stage.

**Per sheet → find tables (region detection):**
- a sheet may hold **N tables** (gaps between them) → segment by blank-row/blank-col runs into regions.
- for each region, find the **real header row**: skip title banners and blank rows; score candidate
  rows on coverage (non-null %), uniqueness, string-fraction, type-consistency of the rows below.
  (`smart_upload.detect_header_row` already does a version of this — extend it.)

**Merged cells (Excel):**
- openpyxl exposes `ws.merged_cells.ranges`. For each merged range, read the top-left value and
  **forward-fill** it into every covered cell before building the DataFrame. Without this, merged
  region labels become nulls and the table is wrong.

**Row-merge / multi-row hierarchical headers:**
- detect 2+ header rows (e.g. `2024 | 2024 | 2025` over `Q1 | Q2 | Q1`). Flatten to a single header
  per column: `2024 · Q1`, `2024 · Q2`, `2025 · Q1`. Forward-fill the parent across its span first.

**Shifted columns / stray cells:**
- if a row's filled-cell pattern doesn't match the header width, flag it (likely a note row or a
  second table starting) → split or drop, surfaced in the preview, never silently merged.

**Per column → `ColumnProfile` (NEW table, the durable understanding):**
| field | meaning |
|---|---|
| `name` / `normalized_name` | original + lowercased/cleaned |
| `dtype` | inferred (int/float/date/text/bool) via DuckDB + override |
| `unit` | ₹ / % / kg / count — LLM + symbol heuristic |
| `null_pct`, `cardinality` | profiling stats |
| `sample_values` | ≤5 representative values |
| `pii_flag` | name/email/phone/id detector → privacy aware |
| `semantic_role` | `id` \| `date` \| `measure` \| `category` |
| `synonyms` | "revenue" ≈ "sales" ≈ "turnover" (feeds agent query matching) |
| `maps_to` | brain entity / canonical column it aligns to (cross-source) |
| `source_ref` | source_file, sheet, col_index (provenance) |

This row is what makes the data **reusable anytime** — the agent and the user both see a column's
meaning, unit, role, and links, not just a bare name.

---

## 6. Data model changes

- **NEW table `column_profile`** — FK to `connection_table` (and/or `data_source_table`), columns per
  §5. One migration, off the true single head (currently `agentconn1`; tuple-down_revision aware).
- **Reuse** `SemanticTable`, `MetricDefinition`, `KnowledgeDoc`, `brain_graph` (AGE) — no schema change.
- **Reuse** `Connection.config` for provenance (`content_hash`, `merged_paths` already there).
- No new store. Queryable tables still land as `ConnectionTable` → DuckDB at query time.

---

## 7. What connects / what can break

**Connects (≈70% already exists):** `SpreadsheetClient`, `smart_upload`, `knowledge_proposer`,
`distiller`, `brain_graph`, DuckDB, OpenRouter client, `file_content_hash` dedup, Knowledge approval
gate, existing `from-file` route + model chain.

**Breaks / risks:**
| risk | severity | mitigation |
|---|---|---|
| **Silent reshape** of user data (wrong header/region) corrupts meaning | 🔴 | preview-before-commit, always; never reshape silently |
| **Greenlet ORM expiry** — `create_data_source_from_file` commits internally → expires ORM objects | 🔴 | capture org_id/user_id/file ids as **strings** up-front; re-query fresh (known landmine) |
| Heavy parser (vision/camelot) in HTTP request path → timeout | 🟠 | run in worker; stream progress; request returns a job id |
| Vision cost on large/scanned docs | 🟠 | route only no-text pages; cache by content hash; cap pages |
| Cross-source join false-positive | 🟠 | propose-only + review gate; show confidence |
| GPU dependency creep | 🟠 | CPU libs default; vision via OpenRouter; Docling optional-only flag |
| New `column_profile` table | 🟠 | migration off true single head; guard PG-only DDL |
| PII leakage into brain/prompts | 🟠 | `pii_flag` → mask in samples; never put raw PII in LLM context |
| Nuxt auto-import for any new FE preview component | 🟠 | filename starts with `<Dir>` or explicit-import |

---

## 8. Phased build

**P1 — messy Excel + profiling (zero new heavy deps, pure CPU, biggest perceived win)**
- port `sheetsense` region/merge/header logic into `services/ingest/` (extend `smart_upload`).
- merged-cell forward-fill (openpyxl), multi-row header flatten, N-table-per-sheet split.
- `column_profile` table + migration + populate in a PROFILE stage.
- preview-before-commit UI on upload.
- flag `HYBRID_INGEST_BRAIN`. Excel/CSV path only.

**P2 — PDF / Word / image (GPU-free)**
- `pdfplumber` + `camelot` for text PDFs; `python-docx` for Word; OpenRouter vision for scanned/image.
- new accepted extensions in the `from-file` route; worker offload + progress stream.
- prose → KnowledgeDoc (existing `ingest_doc`).

**P3 — unify into ONE brain + auto-learn-on-ingest**
- ingest-time trigger → `knowledge_proposer` proposes SemanticTable + MetricDefinition from each new
  dataset (pending).
- UNIFY stage: fuzzy column match across all org sources → AGE join-candidate edges (pending).
- `maps_to` resolution in `ColumnProfile`. Agent context reads the unified brain.

---

## 9. Checklist (per ROADMAP §7)

1. Flag `HYBRID_INGEST_BRAIN` — 3-place in `hybrid_flags.py` (property + UPGRADE_FLAGS + snapshot), OFF.
2. Backend — `services/ingest/` pipeline (DETECT/EXTRACT/PROFILE/UNDERSTAND/UNIFY/STORE), stage
   contracts frozen like `report_delivery/contract.py`.
3. Route — extend `routes/data_source_from_file.py`; worker for heavy stages.
4. Migration — `column_profile` table, off true single head, PG-guarded.
5. FE — upload preview/confirm component (auto-import naming), Studio Add-data entry.
6. Delivery — datasets become normal DataSources → already schedulable/emailable via v1.37.
7. Default OFF; ON for org 55278108 via DB override.
8. Verify ephemeral (hot-cp backend / fe-sync) before bake.
9. DEVLOG + VERSION_HYBRID + CHANGELOG + README + memory + this doc on ship.

---

## 10. North star

> Any file in, fully understood, one brain out. The user never thinks about format or structure —
> they drop data and the agent already knows it, column by column, and how it ties to everything else.
