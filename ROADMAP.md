# CityAgent Analytics — Product Roadmap

> Living plan. How the platform becomes **one product** instead of a pile of features.
> Companion to `CLAUDE.md` (codebase map + landmines) and `DEVLOG.md` (shipped history).
> Last updated: 2026-06-26 · current `VERSION_HYBRID` 1.37.0.
> F09 (Universal Ingest Brain) added 2026-06-26 — supersedes F06; see §9.

---

## 0. The thesis — one spine, one entry point

Everything we ship must collapse onto **one mental model** the user never has to think about:

```
                    ┌──────────────  THE AGENT (chat)  ──────────────┐
                    │  one box. ask anything. it routes.             │
                    └───────────────────────────────────────────────┘
   INGEST            DATASOURCE          ANALYZE           PRESENT          DELIVER
 (many ways in)   (one object)       (agent + tools)    (themed, sticky)  (v1.37 spine)
 upload            ─────────────►     create_data        BI dashboard      scheduled cron
 46 connectors     normalized,        create_artifact    theme presets     clean email
 folder sync       read-only,         compose_dashboard  persistent overlay live dashboard
 web scrape  NEW   RLS, profiled      text tools  NEW                      embed / white-label
 pdf extract NEW                      knowledge layer
 GA / GSC    NEW
 public data NEW
```

**The rule: every new capability enters the product as either (a) a new DataSource type, or
(b) a new agent tool.** Nothing becomes a standalone island. The user types in chat, or clicks
"Add data" — those are the *only two* doors. This is what makes 8 features feel like 1 product.

Why this works for us specifically: we already have the spine. The agent (`agent_v2`), the
auto-registering tool system (`ai/tools/implementations/`), the connector registry
(`data_source_registry.py`), the one-click dashboard-in-chat (`create_data` → `create_artifact`),
and the v1.37 delivery engine (`report_delivery/`) all exist and are proven. The roadmap is
**not new architecture — it's plugging features into slots that already exist.**

---

## 1. Current state (what is already built)

| Layer | Have | Files |
|---|---|---|
| Agent loop | plan/execute/reflect, OpenRouter-only | `ai/agent_v2.py` |
| Tool system | auto-register (drop a file) | `ai/tools/implementations/__init__.py` (pkgutil) |
| One-click dashboard in chat | `create_data` (query→viz) → `create_artifact` (vizs→dashboard/slides) | `ai/tools/mcp/create_data.py`, `create_artifact.py` |
| Artifact render | sandboxed iframe, fullscreen | `components/dashboard/ArtifactFrame.vue`, `utils/artifactIframe.ts` |
| DataSource | 46 connectors, file→DS, DuckDB, RLS | `schemas/data_source_registry.py`, `services/data_source_service.py` |
| BI dashboards | cross-filter, conditional fmt, KPI, Parquet/DuckDB query | P1–P4 (see DEVLOG) |
| Knowledge layer | semantic/metrics/queries + approval gate | `routes/knowledge.py` |
| Scheduled reports (v1.37) | cron → agent run → clean render → per-agent SMTP email | `services/scheduled_prompt_service.py` (`scheduled_run_prompt`), `services/report_delivery/`, `services/notification_service.py` (`send_scheduled_prompt_results`) |
| Delivery renderers | result / dashboard / artifact / workflow, auto-discovered | `report_delivery/renderers/` |
| Embed / white-label | console, per-key origin, embeds | (see CityPharma + Analytics DEVLOG) |
| Flags | `HYBRID_*`, per-org DB overrides, UI toggle | `settings/hybrid_flags.py` |

**Gap = not capability, it's surface + glue.** We can query anything and render anything; we just
don't yet (a) compose a *whole* dashboard from one prompt, (b) let presentation survive refresh,
(c) accept enough ingest types, (d) theme the output.

---

## 2. The 8 features as agent-native slots

Each gap maps to exactly one slot in §0. None is a new app.

| # | Feature | Enters as | Reuses | New code (thin) |
|---|---|---|---|---|
| F01 | Prompt → full dashboard | **agent tool** `compose_dashboard` | create_data ×N + create_artifact | composer that fans out + lays out |
| F02 | Theme presets | **dashboard config** | existing CSS-var theming | token bundles + Appearance dropdown |
| F03 | Persistent edits across refresh | **dashboard config** + v1.37 hook | scheduled_prompt + report_delivery | `config.overlay` + data⊕overlay render |
| F04 | Public datasets (Explore) | **DataSource type** | Parquet store + DuckDB (v1.23) | dataset registry + Explore page |
| F05 | Web scrape → table | **DataSource type** | Playwright (already in image) | scraper client + SSRF guard |
| F06 | PDF → table | **DataSource type** | DocSensei/RO-ED-Lang/sheetsense tech | extractor client (port) |
| F07 | Marketing connectors (GA/GSC) | **DataSource type** | connector framework | 2 API adapters + OAuth |
| F08 | One-click text analysis | **agent tool** `analyze_text` | OpenRouter client | batch tool → derived column |
| F09 | Universal Ingest Brain (any file → one brain) ★ | **DataSource pipeline** + brain | SpreadsheetClient, smart_upload, sheetsense, knowledge_proposer, brain_graph, OpenRouter vision | 6-stage ingest + ColumnProfile + unify-to-one-brain (absorbs F06) |

**Two of eight touch the agent's tool list (F01, F08). Four are pure DataSource adapters
(F04–F07). Two are presentation config (F02, F03).** That's the whole surface area.

---

## 3. How each plugs in — what connects, what breaks

### F01 · Prompt → full dashboard  `compose_dashboard` tool  ★ headline
**Connects to:** the existing chat one-click path. Today the agent *can* do create_data ×N then
create_artifact, but only if it decides to. F01 makes it a first-class, reliable single tool.

- **Where:** new `ai/tools/implementations/compose_dashboard.py` (auto-registers). Surfaced in
  chat ("Build a Q2 sales dashboard…") AND as a `✦ Generate dashboard` prompt bar above the
  Workspace → Dashboards grid.
- **Mechanism:** plan widgets (metrics/grain from schema + approved knowledge) → run N `create_data`
  (parallel if `HYBRID_SUBAGENTS`) → collect viz_ids → `create_artifact(mode="page", viz_ids)` →
  return one dashboard. Each widget stays an editable step.
- **What can break:**
  - 🔴 **Fan-out cost / token blow-up** — N parallel agent calls. Cap N (e.g. ≤6), reuse the
    answer/result cache, gate parallelism behind `HYBRID_SUBAGENTS` (today default OFF — keep it).
  - 🔴 **OpenRouter DNS saturation** — same root cause as the v1.37 transient SMTP `[Errno -5]`.
    Many concurrent calls saturate Docker embedded DNS. Mitigate: bounded concurrency + retry
    (already have the retry idiom in report_delivery).
  - 🟠 **Layout quality** — LLM grid JSON can overlap/clip. Validate layout server-side, clamp to grid.
  - 🟠 **create_artifact auto-selects "top 10" vizs** — with a composer feeding exact viz_ids, pass
    them explicitly; don't let auto-select re-pick. Verify the `viz_ids` param path.
- **Flag:** `HYBRID_DASHBOARD_COMPOSER`.

### F02 · Theme presets  (quick win, ~1–2 days)
**Connects to:** the warm-theme CSS-var migration already done across 148 components.
- **Where:** `frontend/utils/dashboardThemes.ts` (token bundles) + Appearance dropdown on the
  dashboard toolbar. Stored on `dashboard.config.theme` (one string).
- **Mechanism:** theme = `{accent, font, surface, grid, radius}` → re-maps root CSS vars. Widgets
  already read vars → no per-widget change.
- **What can break:** 🟢 low risk. 🟠 dark themes (Executive/Terminal) need contrast pass on
  table zebra + chart text. Embed/white-label brand theme must still win over preset (precedence:
  embed brand > user theme > default).
- **Flag:** none needed (pure styling) — or `HYBRID_DASHBOARD_THEMES` if we want it gateable.

### F03 · Persistent edits across refresh  (extends v1.37) ★ strategic
**Connects to:** v1.37 scheduled reports — the cron + re-run already exist. This makes the output a
*living dashboard*, not just an email.
- **The key idea:** split **data** (refreshed) from **presentation overlay** (sticky).
  `dashboard.config.overlay = { widget_id: {title, series_color, hidden_cols, …} }`. Refresh writes
  new rows to `step.data`; render = `data ⊕ overlay`. Overlay never overwritten by refresh.
- **Where:** add `config.overlay` to the dashboard/artifact; a refresh hook on
  `scheduled_run_prompt` that, when the scheduled prompt targets a dashboard, re-executes the
  widget queries and updates `step.data` (NOT the artifact HTML/overlay).
- **What can break:**
  - 🔴 **Schema drift on refresh** — a renamed/dropped column breaks an overlay referencing it
    (`hidden_cols: ["region_id"]` → column gone). Fail-soft: ignore stale overlay keys, log, don't crash.
  - 🟠 **Two write paths to one artifact** — scheduled refresh vs user live-edit. Need last-writer
    discipline or field-scoped writes (data vs overlay are disjoint → safe if we never co-write).
  - 🟠 **Frontend staleness** — dashboard open while refresh runs. Poll `refreshed_at` or WS nudge.
- **Flag:** `HYBRID_LIVE_DASHBOARD` (or fold into `HYBRID_AGENT_REPORTS`).

### F04 · Public datasets / Data Explorer  (DataSource type)
**Connects to:** Parquet result store + DuckDB path (v1.23 `HYBRID_PARQUET_RESULTS`).
- **Where:** `routes/datasets_public.py` + new top-nav **Explore**. Each dataset = pre-loaded Parquet
  on `ca_uploads` → "Use" registers it as a read-only DataSource on demand → opens chat/dashboard.
- **What can break:** 🟢 low. 🟠 storage size of bundled datasets in the image (keep them on the
  volume / fetch lazily, not baked). 🟠 monthly refresh job per dataset = a small daemon (leader-gated,
  like our other daemons).
- **Flag:** `HYBRID_DATA_EXPLORER`.

### F05 · Web scrape → table  (DataSource type)
**Connects to:** Playwright (already shipped in the image for dashboard PNG) + the SSRF guard pattern
from the DocSensei SharePoint connector.
- **Where:** `data_sources/clients/web_scraper_client.py` + registry entry + Studio **Add data →
  "Scrape a page 🔗"** (4th option next to Folder Sync). `BaseClient` interface: `test_connection`,
  `get_schemas`, `execute_query`.
- **What can break:**
  - 🔴 **SSRF** — user URL could hit internal services (169.254.x, 10.x, localhost, metadata endpoint).
    MUST reuse/extend the DocSensei SSRF allowlist + block private CIDRs. Non-negotiable, security-gated.
  - 🟠 **Playwright contention** — scrape + dashboard PNG share one chromium. Bound concurrency.
  - 🟠 **Brittle parse** — site HTML varies; LLM-clean step + "pick table" UI.
- **Flag:** `HYBRID_WEB_SCRAPE`.

### F06 · PDF / statement → table  ⟶ **ABSORBED INTO F09 (see §3 last block + §9 design)**
**Connects to:** tech we already own elsewhere — DocSensei vectorless PageIndex, RO-ED-Lang customs
PDF pipeline, sheetsense ingestion. poppler + soffice already in the image (used by report_delivery).
- **Where:** `routes/extract_pdf.py` + Studio **Add data → "Extract from PDF 📄"**. Wrap existing
  extractor → emit rows → DataSource.
- **What can break:** 🟠 these live in *other repos* — port a clean module, don't cross-import. 🟠
  big/scanned PDFs need OCR; scope v1 to digital-text tables, flag OCR as v2.
- **Flag:** `HYBRID_PDF_EXTRACT`.

### F07 · Marketing connectors (GA4 / Search Console)  (DataSource type)
**Connects to:** the same connector framework as the 46 existing types.
- **Where:** `data_sources/clients/google_analytics_client.py` + GSC client + OAuth flow + registry
  entries. GA4: sessions/users/conversions; GSC: clicks/impressions/queries/position.
- **What can break:**
  - 🔴 **OAuth secret storage** — Google client secret + per-user refresh token must be Fernet-encrypted
    (same as all creds). NEVER in repo/env-committed. Token refresh on expiry.
  - 🟠 **API quotas / sampling** — GA4 samples large ranges; document + page through.
- **Flag:** `HYBRID_MARKETING_CONNECTORS`.

### F08 · One-click text analysis  `analyze_text` tool
**Connects to:** the org's existing OpenRouter client.
- **Where:** `ai/tools/implementations/analyze_text.py` (auto-registers) + dataset toolbar **Text tools**
  (Sentiment / Keywords / Translate / Summarize). Output = derived column in `staging` schema → then
  chartable/filterable/schedulable like any column.
- **What can break:** 🟠 cost on large columns — batch + cap rows + cache by text hash, fail-soft.
  🟠 derived column must land in `staging` (agent-owned), never mutate the source.
- **Flag:** `HYBRID_TEXT_TOOLS`.

### F09 · Universal Ingest Brain — any dataset → one brain  ★★ flagship
**Supersedes F06.** F06 was "PDF → table." F09 is the bigger idea the user actually wants: **drop in
any file (Excel, CSV, PDF, Word, image), the platform understands its structure deeply, cleans it,
and registers it into ONE org-level brain so the agent knows every dataset and how they relate** —
Compas-style single shared brain, not per-source islands.

**Design doc:** `docs/INGEST_BRAIN_DESIGN.md` (to be written). Summary below.

**GPU-free by construction (we are OpenRouter-only, no local GPU):**
| Input | Parser | Compute |
|---|---|---|
| Excel/CSV | `sheetsense` port + openpyxl (own engine) | pure CPU |
| Text PDF | pdfplumber (text) + camelot (tables) | pure CPU |
| Scanned PDF / image | **OpenRouter vision model** (already wired) | cloud, no GPU |
| Word / PPT | python-docx / python-pptx | pure CPU |
| catch-all (email/html) | Unstructured CPU-mode (optional) | CPU |
Rule: born-digital → CPU lib (fast, free, deterministic). Only scanned/image → vision LLM.
**Docling rejected as default** — its table/layout model is GPU-bound; keep only as optional CPU fallback flag.

**The single brain (one org-level brain for ALL data):**
```
        ┌────────────────  ONE BRAIN (org-level)  ────────────────┐
        │ SemanticTable     what each table is                    │
        │ ColumnProfile     every column: meaning/unit/PII/role   │
        │ MetricDefinition  candidate metrics                     │
        │ brain_graph (AGE) cross-source joins + entity links     │
        │ KnowledgeDoc      prose/glossary from PDF/Word          │
        └─────────────────────────────────────────────────────────┘
            ▲        ▲        ▲        ▲        ▲
         Excel    PDF     Word    image    CSV   → every ingest REGISTERS here
```
Cross-source: brain learns `salesA.cust_id ↔ crmC.customer` across different files → proposes the join.
Agent reads brain at query time → already knows every dataset, no re-scan. All proposals land
`status=pending` (review gate stays). Today the brain fires only on 👎 — F09 adds an **ingest-time
trigger**.

**Deep sheet + column capture (the user's explicit requirement — every column understood):**
- region-detect: N tables in one sheet, find true boundaries (sheetsense)
- find the REAL header row (skip title/blank rows)
- **merged cells** → unmerge + forward-fill value into each covered cell
- **row-merge / 2-row hierarchical headers** → flatten to `parent · child`
- gap rows/cols → drop or split into separate tables
- per column → `ColumnProfile` row (NEW table): `name, normalized_name, dtype, unit, null%,
  cardinality, sample_values[5], pii_flag, semantic_role(id|date|measure|category), synonyms[],
  maps_to(brain entity), source_file, sheet, col_index`

**6-stage pipeline (behind `create_data_source_from_file`):**
```
1 DETECT      sniff type → route to parser
2 EXTRACT     Excel→sheetsense(regions+merge+header)  PDF→pdfplumber/camelot  scan→vision  Word→docx
3 PROFILE     ColumnProfile per column (dtype/unit/PII/role/samples)
4 UNDERSTAND  LLM names each table+column meaning + synonyms (OpenRouter)
5 UNIFY       fuzzy-match columns across ALL sources → propose joins into brain_graph
6 STORE+LEARN tables→ConnectionTable(queryable); prose→KnowledgeDoc; register SemanticTable+
              ColumnProfile+MetricDefinition+graph edges into the ONE brain (pending, review-gated)
```
Storage = existing model chain (DataSource→Connection→ConnectionTable→DataSourceTable). No new store.

**What connects:** reuses `SpreadsheetClient`, `smart_upload` (header/glossary/merge already there),
`knowledge_proposer`, `distiller`, `brain_graph` (AGE), DuckDB, OpenRouter client. ~70% exists.

**What can break:**
- 🔴 **Silent reshape of user data** — wrong table-boundary / header guess corrupts meaning. MUST show
  a **preview before commit**: "Read as N tables, header=row 3, merged col X filled down, dropped 2
  blank rows — fix?" Never reshape silently.
- 🔴 **Greenlet expiry** — `create_data_source_from_file` commits internally → expires ORM objects.
  Capture org_id/user_id/file ids as strings up-front; re-query fresh (known landmine).
- 🟠 **Heavy parsers in request path** — vision LLM / camelot are slow. Run in a worker, not the HTTP
  request; stream progress.
- 🟠 **Cross-source join false-positive** — fuzzy match links wrong columns. Propose-only + review gate.
- 🟠 **Vision cost** — only route scanned/image pages to the LLM; born-digital never hits it. Cache by
  content hash (already have `file_content_hash`).
- 🟠 **New tables** (`ColumnProfile`) — migration off true single head.
- **Flag:** `HYBRID_INGEST_BRAIN` (default OFF). PDF/Word sub-path can reuse the absorbed
  `HYBRID_PDF_EXTRACT` name if cleaner.

**Phases (P1 has zero new heavy deps):**
- **P1** sheetsense port → messy Excel (regions, merged cells, hierarchical headers) + `ColumnProfile`
  table + preview-before-commit. Pure CPU, engine already owned.
- **P2** PDF/Word/image ingest via pdfplumber + camelot + OpenRouter vision (no GPU).
- **P3** unify into the ONE org brain + auto-learn-on-ingest trigger + cross-source join proposals.

---

## 4. Cross-cutting: what connects everything (the glue work)

These are the integrations that make the 8 cohere into one product. Do them once.

1. **Unified "Add data" surface** — one modal, all ingest types (upload · connector · folder sync ·
   scrape · PDF · public dataset). Today they're scattered. `StudioConnectors.vue` becomes the single
   front door. *Connects F04–F07.*
2. **Agent tool catalog awareness** — the agent's planner must know `compose_dashboard`, `analyze_text`
   exist and when to call them (descriptions + examples in `ToolMetadata`). *Connects F01, F08 into chat.*
3. **Dashboard config object** — one schema carrying `{theme, overlay, layout, refresh}`. F02 + F03 +
   F01 all write here. Define it once so they don't collide.
4. **v1.37 as the universal delivery bus** — every produced artifact (chat dashboard, composed
   dashboard, text-analysis result) is deliverable via the same `report_delivery` renderers + per-agent
   SMTP. *Connects everything to email/embed/schedule.*
5. **Knowledge layer feeds the composer** — F01's metric/grain choices should read approved
   semantic/metrics rows (better dashboards on trained agents). *Connects Knowledge → F01.*

---

## 5. Risk register — what can break (ranked)

| Risk | Where | Severity | Mitigation |
|---|---|---|---|
| Fan-out token/cost explosion | F01 composer | 🔴 high | cap widget count, reuse result cache, gate parallel behind `HYBRID_SUBAGENTS` |
| Docker DNS saturation on concurrent LLM | F01, F08 | 🔴 high | bounded concurrency + retry (reuse report_delivery ×3 idiom) |
| SSRF via user URL | F05 | 🔴 high | private-CIDR block + allowlist (DocSensei pattern), security review |
| OAuth/refresh-token leakage | F07 | 🔴 high | Fernet-encrypt, never return, never commit |
| Schema drift breaks sticky overlay | F03 | 🔴 high | fail-soft ignore stale overlay keys |
| Bake/deploy regressions | all | 🟠 med | each feature flag-OFF by default; **never force-recreate onto a stale image** (v1.37 lesson); deploy = rebuild image + verify health+modes, restore via docker cp |
| Alembic head conflicts | F03/F04/F07 (new tables) | 🟠 med | chain off true single head (tuple down_revision aware); flags need no migration |
| Nuxt auto-import invisibility | new `components/<dir>/X.vue` | 🟠 med | filename must start with `<Dir>` or explicit-import (known landmine) |
| Dark-theme contrast | F02 | 🟢 low | contrast pass on tables/charts |
| Two writers to one artifact | F03 | 🟠 med | disjoint fields (data vs overlay), last-writer scoped |
| Playwright contention | F05 vs PNG render | 🟠 med | shared chromium, bound concurrency |
| Image storage bloat | F04 datasets | 🟢 low | lazy fetch to volume, don't bake |
| Silent reshape of user data | F09 ingest | 🔴 high | preview-before-commit; never reshape silently |
| Greenlet ORM expiry on ingest | F09 | 🔴 high | capture ids as strings, re-query fresh (known landmine) |
| Vision/camelot in request path | F09 | 🟠 med | run in worker, stream progress; cache by content hash |
| Cross-source join false-positive | F09 unify | 🟠 med | propose-only + review gate |
| GPU dependency creep | F09 parsers | 🟠 med | CPU libs default; vision via OpenRouter; Docling optional-only |

**Standing deploy landmines (from v1.37):**
- Stack runs ONLY on `docker-compose.build.yaml` (plain compose = different project = empty DB).
- Flags are UI/DB-owned (`hybrid_overrides`) — never re-add `HYBRID_*` to compose/.env.
- Bake = `DOCKER_BUILDKIT=1 docker build -t cityagent-analytics:dev .` then
  `up -d --force-recreate app` — ONLY after verifying the new image contains the code + migration.
  Build can flake at `npm install -g yarn` (network); that's env, not code.

---

## 6. Phased build order (dependency-aware)

```
PHASE R1 — quick wins + presentation spine  (low risk, high polish)
  F02 theme presets        (1–2d, no flag/migration)
  F03 persistent overlay   (extends v1.37; define dashboard.config schema here)
        └─ unlocks "live dashboard" delivery target

PHASE R2 — the headline
  F01 compose_dashboard    (agent tool; needs §4.2 catalog awareness + §4.3 config object)
        └─ depends on R1's config object; reuses create_data/create_artifact

PHASE R3 — ingest breadth  (each independent, parallelizable)
  F09 Universal Ingest Brain  ★ absorbs F06 — build in P1→P3
        P1 sheetsense Excel (regions/merge/hier-header) + ColumnProfile + preview  (CPU, no new deps)
        P2 PDF/Word/image (pdfplumber+camelot+OpenRouter vision, GPU-free)
        P3 unify→ONE brain + auto-learn-on-ingest + cross-source joins
  F05 web scrape  (security-gated: SSRF first)
  F07 GA/GSC      (OAuth)
  F04 public datasets (Explore page)
        └─ all funnel through §4.1 unified Add-data surface
  (F06 standalone DROPPED — folded into F09)

PHASE R4 — analysis surface
  F08 analyze_text (agent tool + dataset toolbar)

PHASE R5 — cohesion + GTM
  §4.1 unified Add-data modal (consolidate R3 entry points)
  §4.5 knowledge → composer wiring
  (optional) free funnel tools / self-serve onboarding — growth, separate track
```

**Rationale:** R1 builds the `dashboard.config` object F01 needs and turns v1.37 into a live-dashboard
engine (compounding value). R2 is the headline once the config exists. R3 features are independent —
fan out (subagents/worktrees) since they touch disjoint files (new client per connector). F06 first
in R3 (port, cheapest). Security-sensitive F05/F07 get review gates.

---

## 7. Per-feature checklist (repeat for each)

1. **Flag** — `hybrid_flags.py`: property + `UPGRADE_FLAGS` entry + `snapshot()` (3-place, or invisible/rejected).
2. **Backend** — tool (`ai/tools/implementations/*.py`, auto-registers) OR connector
   (`data_sources/clients/*_client.py` + `data_source_registry.py` entry) OR config field.
3. **Route** (if needed) — register in `main.py`.
4. **Migration** (only new tables) — chain off true single head; guard PG-only DDL.
5. **FE** — Studio tab/button in `studios/[id]/index.vue` (+ `useAppNav.ts` if new nav group);
   new `components/<Dir>/X.vue` → filename starts with `<Dir>` or explicit-import; restart dev to auto-import.
6. **Delivery** — confirm it renders through `report_delivery` if emailable/schedulable.
7. **Default OFF** — fresh deploy behaves like upstream; ON for org 55278108 via DB override.
8. **Verify live** — ephemeral hot-cp (backend) / fe-sync (FE) before bake; then rebuild + health + modes.
9. **DEVLOG + VERSION_HYBRID + CHANGELOG + README + memory** — every ship bumps all five.

---

## 8. North star

A business owner connects a source (any of 10 ways), types one sentence, gets a themed dashboard that
emails itself every Monday and stays styled the way they left it — all from one chat box, one agent,
one product. We already own the engine. This roadmap is the wiring.

---

*Source conversation: FormulaBot competitive analysis (2026-06-26) → gap list → mockups
(`scratchpad/cityagent-gaps-mockup.html`) → this roadmap. Update this file as phases ship; move
shipped detail to `DEVLOG.md`.*
