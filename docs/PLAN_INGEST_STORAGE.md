# PLAN — Ingest Storage (Parquet) + LLM Merge-Judge

Two upgrades to the file-upload ingest path. Both **flag-gated, default OFF, fail-soft**
(any error → today's behavior). Additive — new modules + hook points, no rewrites.
Backups before touching any existing file (`scripts/backup.sh`).

## Current state (baseline)
- Upload `xlsx/csv` → `SpreadsheetClient._load_frames()` (`pd.read_excel/read_csv`) → DuckDB
  `:memory:` **rebuilt every query** → SQL. Raw file stays on disk; **re-parsed each query/sync**.
- Merge: `_try_merge_same_schema` (`routes/data_source_from_file.py`) = byte-hash dedup +
  **exact column-set equality** (`smart_upload.columns_match`, jaccard 1.0). String-only.
  `merged_paths` = list of raw file paths (all re-parsed on sync).
- Parquet plumbing EXISTS but unused on upload: `duckdb_engine.snapshot_to_parquet`
  (env `FEDERATION_S3_*` / `FEDERATION_SNAPSHOT_DIR`).

Problems: excel re-parse slow (×1000 users), no types/compression/pushdown; merge misses
semantic-same columns (`cust_id` vs `customer_id`), and blind-merges same-name/different-meaning.

---

# TRACK A — Parquet canonical store (storage upgrade)

Goal: parse excel/csv **once** at ingest → write **Parquet** → DuckDB reads parquet direct
(zero-copy, column+predicate pushdown). Raw file kept for lineage/re-ingest only.

Flag: `HYBRID_PARQUET_STORE` (env `HYBRID_PARQUET_STORE`).

### A1 — parquet writer helper (new, pure)
- `app/services/ingest/parquet_store.py`:
  - `to_parquet(frames: dict[str,df], dest_dir, ds_id) -> dict[sheet, parquet_path]`
    (pyarrow; snappy compress; one file per sheet; stamp `_source_label`).
  - `parquet_path_for(ds_id, sheet)` deterministic.
  - never-raise → return `{}` on failure.
- dest: `FEDERATION_SNAPSHOT_DIR` (reuse) or `<uploads>/parquet/<org>/<ds>/`.
- Subtask: choose pyarrow (already a dep via duckdb? verify; else add `pyarrow` to
  `requirements_versioned.txt`, lazy-import).

### A2 — write parquet at ingest
- In `data_source_from_file.py` create path: after frames loaded + cleaned (smart-header),
  if `flags.PARQUET_STORE` → `parquet_store.to_parquet(...)` → store paths in
  `connection.config["parquet_paths"] = {sheet: path}`.
- Append path (`_try_merge_same_schema` merge branch): also write the new file's parquet +
  add to `parquet_paths`.
- Fail-soft: on write fail, leave `parquet_paths` empty → reader falls back to raw.

### A3 — DuckDB reads parquet
- `SpreadsheetClient._load_frames()` / `connect()`: if `parquet_paths` present + files exist →
  `read_parquet(path)` (or DuckDB `read_parquet` directly, skip pandas entirely) instead of
  `read_excel/read_csv`. Else current raw path.
- Best: DuckDB `CREATE VIEW sheet AS SELECT * FROM read_parquet('...')` — no pandas load,
  pushdown intact.
- Subtask: union multiple parquet (merged_paths) → `read_parquet(['a.parquet','b.parquet'])`.

### A4 — verify + bench
- Cold-query before/after (excel vs parquet) row-count match + timing.
- Re-sync uses parquet (no re-parse). Confirm `_source_label` preserved.

**Result:** upload→parquet once; 1st query 10–50× faster, 5–10× smaller, typed, pushdown.
Raw kept only for audit/re-ingest. Default OFF → byte-identical to today.

> Postgres-table ingest (alternative for shared/joined/RLS multi-write) = **not this track**.
> Use existing `staging`/`analytics` dual-schema if a source needs governed PG tables; decide
> per-source later. Parquet+DuckDB covers single-source read-only analytics (the common case).

---

# TRACK B — LLM merge-judge (semantic merge decision)

Goal: LLM as **tiebreaker** on ambiguous column overlap — catch renamed/semantic-same columns,
block same-name/different-meaning + unit traps. Cheap string match stays primary.

Flag: `HYBRID_LLM_MERGE_JUDGE` (env `HYBRID_LLM_MERGE_JUDGE`).

### Decision ladder (only spend LLM when string is ambiguous)
```
byte-identical hash         → DEDUP        (no LLM, free)      ← keep
exact colset match          → MERGE        (no LLM, free)      ← keep
jaccard < 0.6               → new table    (no LLM)            ← keep
0.6 ≤ jaccard < 1.0 (best candidate) → ASK LLM                ← NEW
```

### B1 — column signature helper
- `smart_upload.column_signature(df, sheet) -> {sheet, columns:[{name,dtype,samples:[3]}]}`.
  No raw rows beyond 3 sample values/col (privacy + tokens).

### B2 — merge-judge module (new)
- `app/services/ingest/merge_judge.py`:
  `async judge_merge(db,*,organization,new_sig,cand_sig) -> dict`:
  ```json
  {"verdict":"merge|separate","confidence":0.0-1.0,
   "column_map":{"cust_id":"customer_id","sales_amt":"revenue"},
   "reason":"same grain, renamed cols","unit_warning":null}
  ```
- 1 LLM call, small model (`LLMService().get_default_model(db,org,None,is_small=True)`),
  OpenRouter, strict-JSON, **fail-open = `{"verdict":"separate"}`** (never raise, never
  wrong-merge on error). Same idiom as `ambiguity_gate` / `knowledge_proposer`.

### B3 — wire into route
- In `_try_merge_same_schema`, between exact-match loop and `return None`:
  - compute jaccard vs each candidate; pick best in `[0.6, 1.0)`.
  - if `flags.LLM_MERGE_JUDGE` → `judge_merge(...)`.
  - merge ONLY if `verdict=="merge" AND confidence ≥ 0.8 AND unit_warning is None`.
  - apply `column_map`: rename new file's cols → canonical **before** append (else they
    land as new columns, not unioned). Persist map in `merged_paths[i]["column_map"]`.
  - `unit_warning` non-null → DO NOT merge; surface in response `extra` for user.

### B4 — flag registry (LANDMINE)
- `hybrid_flags.py`: add BOTH `@property LLM_MERGE_JUDGE` AND `UPGRADE_FLAGS` entry AND
  `snapshot()` line. Same for `PARQUET_STORE`. (Missing UPGRADE_FLAGS → per-org override
  silently ignored.) Add to `.env` + compose `${HYBRID_X:-0}`.

### B5 — optional review-gate (decide)
- Auto-merge on LLM verdict (fast) **vs** propose merge → user confirms (safe).
- Recommend: **auto-merge at conf ≥ 0.8, else propose** (hybrid). unit_warning always → propose.

**Result:** renamed/semantic-same files merge into one table (col-mapped); same-name/diff-meaning
+ unit mismatches blocked. Clean exact cases never pay LLM. Default OFF → string-only today.

---

## Build order / parallelism
- A and B are **independent** (different concerns) → can run parallel, disjoint files.
  Shared file = `smart_upload.py` (A: none; B: B1) + `data_source_from_file.py` (A2/A3-reader,
  B3) → serialize edits to those two, or one agent owns each file.
- Suggested fan-out:
  - Agent 1 (Track A): `parquet_store.py` + reader swap + flag.
  - Agent 2 (Track B): `merge_judge.py` + `column_signature` + flag.
  - Parent: wire both into `data_source_from_file.py` (single owner, avoids edit race) +
    backups + `.env`/compose.
- Verify: `import main` clean, single alembic head unchanged (no migrations — config JSON only),
  flag-OFF byte-identical, then flip flags on org 55278108 + smoke.

## Risk / guards
- No migration (both use `connection.config` JSON + files). Zero schema risk.
- Both fail-soft → worst case = today's behavior.
- LLM cost bounded: only ambiguous-overlap uploads (rare); clean cases free.
- Parquet adds disk (kept raw too) — acceptable; can drop raw post-convert later (separate decision).
