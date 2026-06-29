# CLAUDE.md — CityAgent Analytics

Guide for any AI agent working in this repo. This is a **hybrid fork of bagofwords (bow), rebranded Dash**
on branch `hybrid-brain`. Read this before touching anything.

@docs/CODEBASE_MAP.md

## Boot protocol (READ FIRST — do not scan the tree)
You become the codebase expert by READING, not scanning. On session start, these load automatically and
are authoritative: **CLAUDE.md** (this file — rules/current state), **`docs/CODEBASE_MAP.md`** (entry points +
extension patterns + landmines — the expert primer, imported above), **`ROADMAP.md`** (forward plan), and the
HEAD of **`DEVLOG.md`** (recent dated history). That is enough to work fast.
- Do **NOT** read every file or run a full tree scan. Trust the map; open a specific file only when you need
  its exact contents to edit it.
- If the map is missing a path you need, read that one file, then **add it to `docs/CODEBASE_MAP.md`** so next
  session is faster (the map is the durable memory — keep it current, same habit as the DEVLOG/VERSION bump).
- The map covers the load-bearing 20%; `DEVLOG.md` has full per-feature history if you need depth.

## What this project is
Single-project agentic-analytics platform = **Dash chassis** (FastAPI + Nuxt, own AgentV2
plan/execute/reflect loop, ~46 warehouse connectors, multi-tenant, Instructions + approval
gate, MCP, observability) **merged natively** with:
- **dash patterns** (agno-agi/dash) — dual-schema, Engineer view-builder, DB-level read-only.
  Ported as native Dash code. Agno is NOT run. `reference/dash/` is a read-only blueprint only.
- **Karpathy 2nd-Brain** — gated learned memories, reasoning-cache, self-distill, insight
  daemon, entity/correlation graph. All default-OFF, leader-gated.
- **Self-service Skills** — Claude-style SKILL.md + progressive disclosure, scope
  personal/org/global, promote-from-chat authoring.
- **DuckDB federation** — live↔stored 2-way query, cross-source correlation via gated key-map.

Design: `docs/ARCHITECTURE.html` (v0.2). Tasks: `docs/PENDING.md`. Progress log: `docs/PROGRESS.md`.

## HARD RULES
1. **NEVER pull `bagofwords/bagofwords:latest`.** Always build our own image
   `cityagent-analytics:dev` from this repo's Dockerfile. All 3 composes do this.
2. **Pre-pull base images before building** (Docker Hub flakes with `registry EOF`):
   `ubuntu:24.04`, `rust:1-slim-bookworm`, `pgvector/pgvector:pg18` — pull with retry, then build
   runs from cache. (rust is only the qvd2parquet/QlikView converter; ubuntu carries
   chromium/LibreOffice/ODBC — can't drop without rewriting the Dockerfile.)
   `scripts/build.sh` does this pre-pull-with-retry automatically.
   **Split build (refactor):** the heavy runtime apt (LibreOffice, MS ODBC, chromium system
   deps) now lives in `Dockerfile.base` → image `cityagent-base:dev`, built ONCE. The app
   `Dockerfile` is `FROM cityagent-base:dev` and uses BuildKit cache mounts for pip/yarn/cargo;
   JS libs + RDS cert + tiktoken are vendored under `vendor/` (no build-time download). So a
   code-change rebuild no longer re-downloads dependencies (~20min → seconds-2min).
   `Dockerfile.orig` is the pre-refactor backup.
3. **Touch Dash core MINIMALLY.** Prefer new files/modules + hook points over rewrites.
   This is a fork of a fast-moving OSS base; every core edit = future rebase tax.
4. **Everything new is flag-gated** (`app/settings/hybrid_flags.py`), default OFF, so a fresh
   deploy behaves exactly like upstream Dash until a flag is on.
5. **Everything learned is gated** — memories/shared-skills/correlations land in `pending`,
   go live only after approval. Reuse Dash's Instruction build/approval; do NOT build a new gate.

## LLM = OpenRouter ONLY
No Agno → no openai 2.x → Dash keeps `openai 1.107`. Configure as Dash `custom` provider
(`base_url=https://openrouter.ai/api/v1`, per-org DB row, Fernet-encrypted key).
VERIFIED: `app/ai/llm/clients/openai_client.py` `inference_stream_v2` = Chat Completions
streaming tool_calls → OpenRouter-compatible with PlannerV3. Pin **tool-capable** models
(default `anthropic/claude-sonnet-4` + `openai/gpt-4o-mini` router). Seed via
`backend/scripts/seed_openrouter.py` (HTTP, post-onboarding).

## Feature flags (`app/settings/hybrid_flags.py`, env `HYBRID_*`, all default OFF)
`DUAL_SCHEMA · ENGINEER_ASSETS · ANSWER_CACHE · BRAIN_READ · DISTILLER · QUERY_CACHE ·
SKILLS · FEDERATION · BRAIN_GRAPH · INSIGHT_DAEMON · QUOTAS · SEMANTIC_LAYER · METRICS_CATALOG ·
STUDIOS`.
Access via `from app.settings.hybrid_flags import flags`. Env-only daemon knob:
`STUDIO_LEARN_DAEMON_ENABLED` (default 0) + `STUDIO_LEARN_*` thresholds.

## Fast dev lane (FE iteration without rebuild)
Prod image (:3007) serves a compiled `nuxt generate` static bundle — no hot-reload. For daily
frontend work, run the **Nuxt dev server on :3000**:
```
cd frontend && DASH_BACKEND=127.0.0.1:3007 yarn dev   # hot-reload, proxies /api -> ca-app:3007
```
Two lanes: **:3000** = dev/hot-reload, **:3007** = baked prod image (FE changes need a rebuild OR a
generate+`docker cp` FE-sync). `nuxt.config.ts` proxy targets are env-driven (`DASH_BACKEND`, default
8000). Host node22 at `~/.hermes/node/bin` + global `yarn@1.22.22` (no corepack).
- **NEVER run `yarn generate`/`yarn build` while `yarn dev` is live in the same dir** — corrupts
  `.nuxt` → blank app. Recover: kill nuxt, free :3000, `rm -rf .nuxt .output node_modules/.cache
  node_modules/.vite`, restart dev.
- **A new `components/**/*.vue` created mid-session is NOT picked up by Nuxt auto-import until the
  dev server restarts** — the component renders blank, silently. Restart dev after adding any new component.
- FE API calls use `useMyFetch` (auto-injects Authorization + X-Organization-Id, prepends `/api`) →
  use BARE paths (`/knowledge/queries`, NOT `/api/knowledge/...` — double-prefix 404s).

## Knowledge Layer (dash-style semantic model — Phases 0-7 done, flag-gated, approval-only)
Org-shared, per-data-source, gated port of dash's structured Knowledge Layer onto the Dash chassis.
Nuxt page `/knowledge` (nav in `layouts/default.vue`, i18n `nav.knowledge`) with 5 tabs:
**Semantic | Metrics | Queries | Assets | Review** (`pages/knowledge/index.vue`; components auto-imported
from `components/knowledge/`). All routes on ONE router `app/routes/knowledge.py`
(`APIRouter(prefix="/api/knowledge")`, included in main.py). Migration chain off head:
`v1e2c3t4o5r6 → k1nowl2edge3` (semantic) `→ m2etrics3cat4` (metrics) `→ q3uery4lib5` (query lib)
`→ b4rain5graph6` (brain_graph_edges); **head `b4rain5graph6`** (single head, applied).
- **Semantic** (`models/semantic_table.py`, `flags.SEMANTIC_LAYER`): per-table description/use_cases +
  per-column meaning. `GET /semantic?data_source_id=` seeds empty rows from schema (idempotent).
- **Metrics** (`models/metric_definition.py`, `flags.METRICS_CATALOG`): name→definition→table_ref→sql_calc.
  `POST /metrics/{id}/test` runs sql_calc read-only (`_is_read_only_sql` guard + `get_client().aexecute_query`, 100-row cap).
- **Queries** (`models/query_library.py`): saved SQL + `POST /queries/{id}/run` (same guard/executor, run_count++).
- **Context wiring (Ph4)**: only `status=='approved'` rows reach the agent. Builders
  `context/builders/{semantic,metrics}_context_builder.py` + sections + tool `resolve_metric`
  (native `tools/implementations/`, auto-registered). Render path (all 4 steps or it silently no-injects):
  `builder.build()` → `ContextHub._static_cache` → `get_view()`→`StaticSections` → `agent_v2.py` `.render()`
  appends to planner instructions. **Touches 3 core files** (`context_hub.py`, `context_view.py`, `agent_v2.py`)
  — mirrors the brain/skills path exactly; rebase-tax noted.
- **Self-learning (Ph5)**: `app/ai/brain/knowledge_proposer.py` fires after the distiller on 👎
  (gate `DISTILLER AND (SEMANTIC_LAYER OR METRICS_CATALOG)`) → UPSERTs `status='pending'` proposals (never
  overwrites approved). Trigger in `completion_feedback_service.py` (same fresh-session/reload-by-PK/strong-ref
  discipline as distiller). `GET /knowledge/pending` + `POST /knowledge/{kind}/{id}/approve|reject`
  (kind∈semantic|metric|query; reject is soft→'rejected'). FE Review tab. Pending rows are auto-invisible
  to the agent (approved-only invariant). No migration — `status` is a plain String, 'pending' just works.
- **Engineer Assets (Ph6)**: SURFACES existing assets — NO new model/migration. `build_data_asset` tool
  already records each `analytics.*` view as an `Instruction` (`category='data_asset'`, `ai_source='engineer_asset'`,
  `structured_data={object,kind}`). `GET /knowledge/assets` reads those rows (org-scoped, flag `ENGINEER_ASSETS`,
  empty when OFF) + `POST /knowledge/assets/{id}/approve|reject` flips Instruction.status published↔draft.
  Schema `schemas/knowledge_assets_schema.py`. FE `AssetsTab.vue`. Assets carry NO per-DS link → `data_source_id`
  is echo-only. LANDMINE: register `/assets/{id}/approve` BEFORE the catch-all `/{kind}/{id}/approve` (else 'assets'
  treated as a pending-kind).
- **Embed + AI-suggest (Ph7)**: all 5 tabs take optional `dataSourceId` prop → pin DS + hide picker
  (`showPicker`/`activeDataSourceId`). Reusable `components/knowledge/KnowledgePanel.vue` (props `dataSourceId?`,
  `hideReview?`) owns tab bar + AI-suggest button; `pages/knowledge/index.vue` is now just `<KnowledgePanel/>`
  (picker mode). Embedded `<KnowledgePanel :dataSourceId>` in per-DS `pages/onboarding/data/[ds_id]/context.vue`.
  **AI-suggest**: `POST /knowledge/ai-suggest/{data_source_id}` body `{focus:semantic|metrics|both}` — introspects
  schema (`get_client().get_schemas()`, cap 40 tbl/30 col), LLM extracts table descs + metrics, writes `status='pending'`
  via Phase-5 `knowledge_proposer` helpers (new fn `propose_knowledge_from_schema`, approval-safe, never raises) →
  Review tab. Flag gate (`SEMANTIC_LAYER or METRICS_CATALOG`) short-circuits to `{disabled:true}` BEFORE DS lookup/LLM.
  Button renders only when DS pinned (needs concrete schema). Skeletons gated `loading && !items.length`.
NOT yet baked into the image — lives via `docker cp` + dev :3000 (Phase 8 = rebake). Schema file is
`query_library_schema.py` (NOT `query_schema.py` — that's Dash core, don't clobber). New Nuxt component → restart
dev server (auto-import scans on start only). Parallel agents on same file race → confirm on disk after.

## Coding gaps closed (2026-06-18, "finish coding before build") — C1-C4, all flag-gated/default-OFF, NOT committed
Before the Phase-8 bake, four incomplete code paths were finished (subagents, disjoint file ownership to avoid races):
- **C1 BRAIN_GRAPH** — was a flag with **0 consumers, no module**. Built pgvector + recursive-CTE graph
  (**NOT Apache AGE** — AGE dropped, not PG18-ready): migration `b4rain5graph6` + `brain_graph_edges` table,
  `models/brain_graph_edge.py`, `ai/brain/brain_graph.py` (`propose_edges_from_entities` pending/approval-safe +
  `neighbors()` multi-hop CTE), `ai/context/sections/brain_graph.py` + `builders/brain_graph_context_builder.py`,
  wired into `context_hub.py` (`render_brain_graph_section`) + `agent_v2.py` (after BRAIN_READ block). OFF → empty, no DB hit.
- **C2 serving-funnel tiers** — Tier ① answer-cache was already real (only stale "NOT built" comment removed);
  **Tier ③ matview built** (`analytics_engine.py`: `pg_matviews` scan + conservative single-match serve, gated `DUAL_SCHEMA`).
  Funnel order ①→②→③→④ intact; only helper bodies/docstrings changed, not the funnel dispatch.
- **C3 FEDERATION** — `duckdb_engine.snapshot_to_parquet` was `NotImplementedError`; now writes Parquet to S3/MinIO
  (httpfs, env `FEDERATION_S3_*`) or local fallback (`FEDERATION_SNAPSHOT_DIR`), honors `freshness.py` TTL. DuckDB
  `federate()` wired into `code_execution.py` behind `flags.FEDERATION` AND only when run spans ≥2 sources; bounded
  `memory_limit`/spill/threads. No new table/migration (env-driven config). OFF → code-exec byte-identical.
- **C4 skill top-K** — `skill_context_builder.py` was inject-all; now top-K (K=8, `HYBRID_SKILLS_TOP_K`), user-scoped,
  ranked by **token-Jaccard** (reused reasoning-cache idiom — **no embeddings client exists in repo**; a future
  C1-owned migration could add a pgvector column + OpenRouter embeddings and swap `_rank_skills`). Graceful fallback to full catalog.
Verified: single alembic head `b4rain5graph6`, `import main` OK (456 routes), all flag-OFF paths clean no-op.

## Why the Knowledge tabs look empty (NOT a bug — earned/learned layers)
Fresh install + no agent traffic = empty by design. **Semantic** is the only auto-seeded tab (table/column skeletons
from the DS schema on first open; descriptions blank until AI-suggest/human fills → 0% described). **Metrics/Review**
fill from AI-suggest or distiller (👎). **Queries** fills from `QUERY_CACHE` capturing proven SQL on real chat answers.
**Assets** needs `ENGINEER_ASSETS` ON + a `build_data_asset` run. If a tab is *totally blank* (no picker, no empty-state),
that's the stale-dev-server landmine above → restart `yarn dev`.

## "AI Analyst" → "City Agent Analyst" (renamed platform-wide)
FE (`pages/index.vue`, `settings/general.vue`) + BE defaults (report_schema, organization_settings_schema,
ai/agent_v2.py, organization_service, report_service). LANDMINE: a stored
`organization_settings.config.general.ai_analyst_name` overrides the code default → also UPDATE the DB row
(`config` is `json` not jsonb → cast: `jsonb_set(config::jsonb, '{general,ai_analyst_name}', '"City Agent Analyst"')::json`).

## Build & run (local dev, own image)
```
# 1. one command: pre-pulls bases (with retry), builds cityagent-base:dev ONCE,
#    then builds the app image cityagent-analytics:dev via docker-compose.build.yaml.
bash scripts/build.sh
#    Force a base rebuild when system deps (LibreOffice/ODBC/chromium) change:
#    bash scripts/build.sh --rebuild-base
# 2. run our image
docker compose -f docker-compose.build.yaml up -d
curl localhost:3007/health     # ports: APP=3007 (internal 3000), POSTGRES=5439 (see .env)
```
`scripts/build.sh` is the entry point: it pre-pulls `ubuntu:24.04`/`rust:1-slim-bookworm`/
`pgvector/pgvector:pg18` with retry, builds the heavy runtime base `cityagent-base:dev` once
(skipped if it already exists; `--rebuild-base` forces it), then builds the app image. After
the one-time base build, code-change rebuilds are seconds-2min (BuildKit cache mounts +
vendored deps under `vendor/`, no re-download). `Dockerfile.orig` is the pre-refactor backup.

DB = **PostgreSQL 18 + pgvector** (`pgvector/pgvector:pg18`). AGE dropped (not PG18-ready) →
2nd-brain graph = pgvector table + recursive CTE. Migration head `v1e2c3t4o5r6` enables the
`vector` ext. First-ever build (base + app) ~20min (frontend `nuxt generate` forces 6GB Node
heap — give Docker ≥10GB or build stages serially via `--target` so the generate runs alone).

## Boot status (VERIFIED LIVE 2026-06-18)
Full stack builds + boots green. First-run admin via `POST /api/auth/register`
(`{email,password,name}`; first uninvited user auto-creates an org + becomes admin).
Dev admin: `admin@cityagent.io` / `CityAgent#2026` (org "Main Org"). OpenRouter seeded via
`backend/scripts/seed_openrouter.py` (DASH_BASE_URL/DASH_ADMIN_EMAIL/DASH_ADMIN_PASSWORD/
OPENROUTER_API_KEY env); default analysis `anthropic/claude-sonnet-4` + router `openai/gpt-4o-mini`.
**Smoke 1.4 PASSED** — planner ran, claude-sonnet-4 answered through OpenRouter, completion
`status=success`. **A.1 PASSED (2026-06-18) — FULL native tool_use**: chinook demo (`POST
/api/data_sources/demos/chinook`) → `refresh_schema` (11 tables auto-active) → report → agent
ran `create_data` tool → `SELECT COUNT(*) FROM Artist` → "275 rows". Smoke script `/tmp/smoke_a1.py`.
API gotchas: all org-scoped calls need header `X-Organization-Id: <org id from GET /api/organizations>`;
login `POST /api/auth/jwt/login` form-encoded `username/password`; report create body uses
`title` (not name) + `data_sources` (NOT data_source_ids — silently ignored → unlinked report);
`POST /reports/{id}/completions` returns thin body, poll `GET /reports/{id}/completions` for blocks/answer.

**Phase A flag proofs ALL PASS (2026-06-18, flags ON via `.env`):** A.2a/b ANSWER_CACHE funnel ①
(warm 0.2s/157ms vs cold ~20s, `GET /api/funnel/stats` by_tier); A.2c DISTILLER (👎 → ai/learned
pending Instruction, live); A.2d SKILLS (author draft skill from completion). Two real bugs were
found + fixed in our hybrid code: (1) `app/ai/brain/qa_pair.py` resolves Q+A across Dash's TWO
sibling Completion rows (user row=`prompt`, system row=`completion`, paired by `turn_index`) —
distiller + skill-authoring previously read both from one row → got half → no-op; (2) the live
👎 distill worker reloaded org/user by PK in its own session (were detached) + keeps a strong
task ref (asyncio GC). Toggle flags: set `HYBRID_X=1` in `.env` → `up -d --force-recreate app`
(compose lists all 11 as `${HYBRID_X:-0}`, default OFF).

**FULL REBUILD BAKED (2026-06-18) — durable `cityagent-analytics:dev`:** babel pinned 7.26.4
(artifact render fix), CityAgent logo swapped platform-wide (`frontend/public/assets/logo.png` +
`logo-128.png` + `favicon.ico`, source master `cityagent-logo-source.png`), Intercom REMOVED
entirely (module + boot + config + links, 0 refs in bundle), Documentation nav button removed
(left sidebar + home; 3 enterprise `docs.bagofwords.com` help-links inside Settings pages remain).
FE is a compiled static bundle (`nuxt generate` → `.output/public` → served `/app/frontend/dist`);
`.vue`/config edits need a REBUILD to show (no prod hot-reload). Backend `.py` can be hot-iterated:
`docker cp <f> ca-app:/app/backend/... && docker exec ca-app /opt/venv/bin/python -m py_compile <f>
&& docker restart ca-app` (restart preserves cp'd files + flag env; `--force-recreate` reverts to
image). Standalone in-container scripts: `cd /app/backend && PYTHONPATH=/app/backend
/opt/venv/bin/python s.py`, and `import main` first to register all ORM models.

## Conventions
- New tools → `app/ai/tools/implementations/*.py` (auto-registered by ToolRegistry; just drop the file).
  Schemas → `app/ai/tools/schemas/`. Events → `app/ai/tools/schemas/events.py`.
- New context → `app/ai/context/builders/` + register in `context_hub.py`.
- Migrations → chain off the **true single head** (verify: a revision no one lists as
  `down_revision`, accounting for **tuple** down_revisions in merge migrations). Guard
  Postgres-only DDL with `op.get_bind().dialect.name == "postgresql"` (SQLite has no schemas).
- Tests → `backend/tests/unit/` for deterministic mocked tests (run in CI); `@pytest.mark.e2e`
  / `@pytest.mark.ai` for DB/LLM integration.
- Agent-owned schemas in Dash's managed Postgres: `analytics` (Engineer views), `staging` (ingest).
  External connections stay read-only via Dash's existing query path.

## Landmines (learned the hard way)
- Alembic has merge migrations with **tuple** `down_revision` — naive head-finding gives false
  multiple heads. True head (at fork time): `d6d9a78b7b4a`.
- Docker Hub `registry EOF` on base pulls — pre-pull with retry (rule 2).
- `dev`/`build` composes shipped `image: bagofwords/bagofwords:latest` + `pull_policy: always` —
  replaced with build-from-source. Don't reintroduce.
- Dash base error class is `app.errors.app_error.AppError(error_code, message, status_code=...)`,
  NOT `app.errors.AppError`.
- The analytics write guard must check only the **write target's** schema, not every schema
  referenced — an analytics view legitimately SELECTs from public/company data.
- **PG18 data dir**: PG18 images store data in `/var/lib/postgresql` (major-version subdir), NOT
  `/var/lib/postgresql/data`. Mounting `/data` → container errors `unhealthy` on boot. All composes
  mount the parent. (Re-mount → drop the old empty volume first.)
- **`--target` cache ≠ compose cache**: pre-building stages with `docker build --target X` does NOT
  feed `docker compose build`'s cache — compose re-runs the whole Dockerfile. To serialize for RAM,
  build `--target` AND accept compose re-runs, or just `docker compose build` direct (parallel).
- **rtk mangles `docker logs`/`grep`**: it returns a summarized stub. Use `rtk proxy docker logs <c>`
  for raw container logs; read large files with the Read tool, not piped `grep`.
- Email validator rejects `.local` TLD (reserved) — use a real-format domain for admin email.
- Curl'd API JSON can carry control chars (planning glyphs) → `json.loads(..., strict=False)`.
- **Artifact render "Cannot use import statement outside a module"** (blank dashboard): vendored
  `@babel/standalone` must stay PINNED to 7.x in `scripts/download-vendor-libs.sh`. Babel 8
  defaults preset-react `runtime:'automatic'` → injects `import {jsx} from "react/jsx-runtime"`
  into the classic `<script type="text/babel">` (artifact code inlined raw by
  `frontend/utils/artifactIframe.ts`). 7.26.4 = classic runtime → `React.createElement` + global
  React, no import. Do NOT unpin.
- **FE changes are invisible until rebuild** — prod image serves a pre-compiled `nuxt generate`
  bundle, no hot-reload. Backend `.py` is hot-iterable via `docker cp`+`py_compile`+`docker restart`.



## Parked feature branches (built, NOT merged, NOT baked, flags OFF — 2026-06-29)
Three large features built phase-by-phase on isolated branches off `main`, each flag-gated default-OFF,
pushed to origin, **never merged to main**. With flags OFF the running product is byte-identical. Each has
a full memory file (see MEMORY.md). Tail work (live-run, FE-wire, auto-learn) noted per feature.
- **`feature/smart-dashboard`** — Outputs "Generate dashboard" → smart builder: auto-context from the chat
  turn + the agent's OWN bound sources (no picker), Auto model, ONE clarify chip only when blind. Flag
  `HYBRID_SMART_DASHBOARD`. NEW `routes/smart_dashboard.py` (context + smart-generate) + `report_slides.
  _generate_artifact` gains optional `steer_prompt/depth/size` + FE `components/dashboard/SmartBuildSheet.vue`
  (`<DashboardSmartBuildSheet>`). Reuses `_generate_artifact`+`ambiguity_gate`+`sense_maker`. = ROADMAP F01.
- **`feature/ingest-brain`** — Universal Ingest Brain (ROADMAP F09). Sidecar pkg `services/ingest_brain/`
  (≠ existing `services/ingest/`): messy-Excel (merged cells / N-tables / hier-headers) + per-column
  `column_profiles` (mig `colprofile1` off `sessumm1`) + PDF/Word/PPT + scanned/image vision + email/HTML/
  legacy-.xls + cross-source UNIFY joins. Flag `HYBRID_INGEST_BRAIN`. Pure-python tested; STORE auto-learn
  + live vision = tail. Adds OPTIONAL deps `camelot-py`/`ebooklib` (lazy, missing→degrade).
- **`feature/mixture-of-agents`** — MoA: 4 diverse models analyse in parallel → glm-5.2 writes. `POST
  /llm/moa/test`. Resume = register a virtual `moa/` picker model + AgentV2 hook.

## Changelog → `DEVLOG.md`

The full dated per-feature changelog (every `## YYYY-MM-DD` entry from 2026-06-19 on) now lives in
**`DEVLOG.md`**. This file stays the living map: rules, current state, landmines. When you finish a
feature, append the dated entry to `DEVLOG.md` (not here) and update the relevant map section above
if the current state changed.

## Intelligence Layer (dash-parity, 2026-06-25 — see DEVLOG)
8 capabilities closing the gap vs `reference/dash` prompt-context layers. All flag-gated default-OFF,
additive. Flags in `hybrid_flags.py` (each needs @property + `UPGRADE_FLAGS` entry + `snapshot()`):
`HYBRID_PROFILE_V2` (P1 Deep Profiler + P5 Lazy Profile), `HYBRID_PROACTIVE_INSIGHTS` (P2),
`HYBRID_FORECAST` (P3, needs prophet bake), `HYBRID_GOLDEN_QUERIES` (P4), `HYBRID_CODE_ENRICH` (P6),
`HYBRID_VERIFIED_METRICS` (P7), `HYBRID_SEMANTIC_SEARCH` (P8 scaffold). Mig chain
`resultcache1 → goldenq1 → verifmetric1 → hybridsearch1`.
- **UI**: Studio rail group `intelligence` (`pages/studios/[id]/index.vue`), 8 tabs `i_*` →
  `components/studio/StudioIntelligence.vue` (live fetch + real toggle via existing hybrid-flags PUT).
- **Data API**: `routes/intelligence.py` `GET /api/intelligence/layer/{layer}?studio_id=` — read-only,
  org-scoped, fail-soft. profiler/codeenrich=metadata_json, metrics/golden=DB, search=BrainGraphEdge,
  lazy/insights/forecast=note (transient).
- **Default-ON org 55278108**: PROFILE_V2, VERIFIED_METRICS, GOLDEN_QUERIES, PROACTIVE_INSIGHTS via
  `config['hybrid_overrides']`. OFF: CODE_ENRICH (cost), FORECAST (prophet), SEMANTIC_SEARCH (scaffold).
  Per-org flag auto-inherits to all/new agents; true per-agent resolver NOT built.

## Agent Templates — share an agent's best practices (2026-06-25, BAKED)
Export a Studio's data-agnostic know-how (rules/metric-formulas/example-patterns/skills/persona) as a
portable versioned template; others bind it to their columns → their own agent. Flag `HYBRID_AGENT_TEMPLATES`.
- Model `agent_template.py` (`AgentTemplate`: slug+version, scope org/global, status draft/published,
  body_md + manifest JSON). Mig **`agtmpl1`** off `chlogseen1`. Head now `agtmpl1`.
- Contract: frontmatter `requires_columns:[{role,as}]` + `{as}` placeholders in body. Export
  generalizes columns→`{role}` via profile_v2 roles. Placeholder scheme = role-lowercased,
  index-suffixed for dupes (`{measure}`,`{measure_2}`); `requires_columns` = placeholders actually used.
- Services `app/services/templates/`: `exporter.py` (studio→template, strips data/creds),
  `parser.py` (frontmatter, PyYAML+hand-rolled fallback), `binder.py` (auto_match via difflib —
  no embeddings; apply_binding; `instantiate_template` → new Studio, items born **pending**, skills via
  StudioBoundPack, metrics draft). Routes `routes/agent_templates.py` `/api/templates`:
  list/detail/publish/import/delete + `from-studio/{id}` (export) + `{id}/bind-preview` + `{id}/instantiate`.
  All flag-gated + fail-soft. Registered main.py.
- FE: nav **Templates** in Studios group; `pages/templates/index.vue` (gallery) + `[id].vue` (detail) +
  `components/templates/BindWizard.vue` (4-step). **Export as Template** button in studio header
  (`studios/[id]/index.vue`, gated canEdit). Raw golden SQL OFF by default in exports.
- E2E verified live (org 55278108, flag ON): export CRM→template → list → publish → bind-preview →
  instantiate → new Studio created. LANDMINE: `requires_columns` empty until the source studio has
  profile_v2 (train it first); imported items always pending (review gate).
- **v1.4.1 popup journey:** `BindWizard.vue` = MODAL (v-model) from gallery card, 5 steps
  Preview→Data→Map→Review→Build (Map auto-skipped unless existing-source+requires). Step 2 = 3-way
  (existing / connect-upload / **skip**). `instantiate` route ALLOWS empty data_source_ids (skip =
  agent now, placeholders intact, bind later). Gallery "Use template"→openWizard (in place);
  card click→detail.
- **v1.4.2 Studios page UX:** `StudioCard.vue` lifecycle chip draft(no src)→ready(src,0 chats)→
  live(active<7d)→idle from source_count/chat_count/last_active_at — replaces live/idle dot + the
  4-zero stat grid; per-card next step (draft→Add data + "connect data"; ready→train hint;
  live/idle→real stats + Open/Chat); action bar persistent (was hover-only). Removed duplicate ghost
  add-card in `pages/studios/index.vue` (top-right = only add). Demoted nav "New report" to outline
  (`nav/TopNav.vue`) — one filled primary per zone.

## PWA — installable desktop/mobile app (2026-06-25, BAKED)
App installs from the browser (standalone window, dock icon, offline shell). Module `@vite-pwa/nuxt`.
- `nuxt.config.ts` `pwa{}`: manifest (name/short_name, `display:standalone`, `start_url:/`,
  `theme_color #C2683F`, icons 192/512 + maskable), `registerType:autoUpdate`, `devOptions.enabled:false`.
- workbox: `navigateFallback:'/'`, precache shell; **`/api` + `/ws` = `NetworkOnly`** (never cache
  API/auth/data); `_nuxt/*` CacheFirst. `globIgnores` the giant editor blobs (Monaco TS worker ~9MB,
  babel ~3MB) + `maximumFileSizeToCacheInBytes:4MB` — else `yarn generate` ERRORS on precache size.
- icons in `frontend/public/`: `pwa-192x192.png`, `pwa-512x512.png`, `pwa-maskable-512x512.png`,
  `apple-touch-icon.png` (generated from `assets/logo-mark-512.png` via PIL).
- `components/nav/InstallApp.vue` — one-click Install button (catches `beforeinstallprompt`, shows only
  when installable + not already standalone), wired into `nav/TopNav.vue` left of the bell.
- SPA (`ssr:false`) → manifest link + SW register are injected at RUNTIME by the module plugin, NOT in
  static index.html (curl of `/` won't show them; they're in the JS bundle — verify there).
- LANDMINE: **prod install needs HTTPS** (localhost exempt for testing); without TLS the prompt + SW
  silently don't activate. iOS = manual Share→Add to Home Screen (no programmatic prompt). Silent
  zero-click auto-install is impossible in any browser — the button is the 1-click path.

## Rebrand → City Agent Insights + new logo (2026-06-25, v1.8.0, BAKED)
- **Logo**: new brand PNG (transparent — the orange preview bg is alpha 0) processed via PIL from
  `~/Downloads/ChatGPT Image Jun 25 ...`. Overwrote `frontend/public/assets/`: full logo (mark+"CityAgent
  INSIGHTS") → `cityagent-dash-logo.png` (home) + `cityagent-insights-logo.png`; square C-mark → `logo-mark.png`,
  `logo-128.png`, `logo-mark-128/512.png`, `logo.png` (nav `TopNav.vue`, sign-in, onboarding, chat avatar — all
  reference these filenames, so no .vue change needed for the mark). LANDMINE: original PNG has a tall faint glow
  → trim/crop with a SOLID-alpha threshold (>90), not `getbbox()`, else huge empty padding.
- **Rename** "City Agent DASH" → "City Agent Insights" everywhere (sed over index.vue, settings/general.vue,
  SlidesPanel.vue, sign-in.vue + backend defaults report_schema/organization_settings_schema/agent_v2/
  organization_service/report_service). Org 55278108 DB `config.general.ai_analyst_name` also patched.
- **Sign-in** (`pages/users/sign-in.vue`): wordmark span DASH→Insights, greeting + footer updated, logo wrapper
  gradient → white box (mark has its own orange C), **sign-up block removed**.
- **LDAP enabled by default**: `organization_settings_service.get_ldap` default `enabled` False→**True**
  (UI shows it on). Login auth uses GLOBAL `dash_config.ldap` (unaffected — no break risk); per-org enable only
  drives the EE admin UI + sync. Org 55278108 `config.ldap.enabled=true` set in DB too.

## Slide workspace — "Open" a presentation (2026-06-25, v1.7.0, BAKED)
Fix: "Open" on a deck (`pages/presentations/index.vue` `openSlides` → `/reports/{id}?focus=slides`) used to
show the deck + the FULL report conversation (clutter). Now it's a clean slide workspace.
- `pages/reports/[id]/index.vue`: new `slidesFocus` ref (set in the `focus==='slides'` branch, cleared in
  `exitDashboardFirst`). When ON: left = deck only (the dock **tab strip hidden**, `v-if="!slidesFocus"`);
  the in-file header shows **"Edit & analyze slides"** + a Chat-first button instead of `ReportHeader`; a hint
  chip **"Ask to edit a slide or analyze the deck…"** sits above the unchanged `PromptBoxV2`. LANDMINE noted:
  `PromptBoxV2` placeholder + `ReportHeader` title are computed INSIDE those child components (no override
  prop) → framing done in-file rather than mutating children (one-file constraint). Empty deck (0 slides/0 viz,
  e.g. "Monthly EBITDA") → in-file clay empty state "No slides yet — ask chat to create a deck".
- `components/dashboard/ArtifactFrame.vue`: expand ⛶ now = TRUE fullscreen — Fullscreen API on a Teleported
  `fixed inset-0 z-[100]` overlay wrapper (NOT the sandboxed iframe), auto-falls-back to the overlay if the API
  rejects; Esc + ✕ close (synced via `fullscreenchange` + keydown, listeners removed on unmount); icon swaps to
  `arrows-pointing-in`. SlideViewer re-rendered large, prev/next stays usable. PPTX/version dropdown untouched.
- `pages/presentations/index.vue`: button tooltips (Open = slide workspace, Open in chat = conversation);
  0-slide decks show a "No slides yet" chip + relabel Open → **"Open & generate"** (`slideCount(p)` helper).

## Whole-folder upload (one-shot, browser) (2026-06-25, v1.6.0, BAKED)
DIFFERENT from Folder Sync (below): a one-shot browser folder pick, no desktop app, no flag.
`components/data/UploadSpreadsheetModal.vue` — added a 2nd hidden `<input webkitdirectory directory multiple>`
+ "Upload a whole folder" button + `onFolderInput` (filters `.xlsx/.xls/.csv`, drops `~$` lock files) →
reuses the existing `batchUpload()` (each file → `/files` → `/data_sources/from-file`, auto-pins via
`created` emit). No backend change. Folder Sync ⟳ = continuous; this = grab-everything-once.

## Folder Sync — local folder auto-ingest, "like Claude Code" (2026-06-25, BAKED)
A desktop tray agent watches a local folder and pushes changed Excel/CSV files to the server; each
push delta-upserts into a per-agent DataSource. Flag `HYBRID_FOLDER_SYNC` (default OFF; ON org 55278108).
- **Server delta ledger** `folder_sync.py` (`FolderSyncState`: org, user, machine_label, source_path
  [the upsert key], file_hash sha256, file_id, data_source_id, studio_id, status new|updated|skipped|error,
  last_sync_at). Unique idx (org, source_path). Mig **`foldersync1`** off `agtmpl1`. **Head now `foldersync1`.**
- **Route** `routes/sync.py` (paths declared w/o `/api`, included w/ `prefix="/api"` in main.py):
  - `POST /api/sync/file` (hot path, multipart `file`+`source_path`+`sha256`+`machine_label`+`target_studio_id`):
    unchanged hash→`skipped` (no ingest); new path→ingest+`new`; changed hash→re-ingest+`updated`. Reuses
    `file_service.upload_file` + `create_data_source_from_file` (which already does content-hash dedup +
    same-schema merge → edited file feeds the SAME source). Optional Studio bind via StudioDataSource.
  - `GET /api/sync/status` (machines grouped), `GET /api/sync/agents` (org Studios for the tray dropdown),
    `POST /api/sync/key` (mint `bow_` key, plaintext once).
  - **Auth = `mcp_auth`** (reused from routes/mcp.py): JWT OR `X-API-Key` `bow_` key → headless agent pairs
    with just a key. All flag-gated.
- **LANDMINE (greenlet):** `create_data_source_from_file` commits internally → expires ALL ORM objects in
  the session. Touching `user.id`/`organization.id`/a pre-ingest `row` after it triggers a SYNC lazy reload
  → `MissingGreenlet`. FIX: capture `org_id`/`user_id`/`file_name` as strings up-front, and **re-query** the
  ledger row fresh after ingest. Never touch the expired ORM objects.
- **LANDMINE:** `StudioDataSource` has ONLY `studio_id` + `agent_id` (no `organization_id` column) —
  passing org_id to its ctor → `TypeError invalid keyword`. Org-scope via the verified Studio instead.
- **FE:** `components/studio/FolderSyncCard.vue` (per-agent card on Sources tab: empty→"Set up folder sync",
  live→folder/N files/synced-ago + Manage), `components/sync/FolderSyncSetupModal.vue` (3-step: download
  app / generate key / pick folder; `POST /sync/key`), `components/sync/FolderSyncPanel.vue` +
  `pages/settings/folder-sync.vue` (connected machines, folder→agent map, status pills). "Add data → **Sync
  a folder ⟳**" 3rd option in studio Auto-pilot STEP 1 (`studios/[id]/index.vue`). Settings tab in
  `layouts/settings.vue` + `nav/TopNav.vue` Manage→Settings. All `useMyFetch` BARE paths.
- **Desktop agent** (standalone, NOT in image, NOT deployed): `folder-sync-agent/` — `sync_agent.py`
  (stdlib + `requests`+`watchdog`; `setup`/`run`/`status`/`agents` CLI; `~/.cityagent-sync/{config,state}.json`;
  sha256 local-state delta, atomic writes; sends `X-API-Key`; debounced watcher; deletes ignored) +
  optional `tray.py` (pystray/Pillow) + README.
- **Download (v1.5.1, WORKING):** `GET /api/sync/download/{macos|windows|linux}` (in sync.py) — PUBLIC (no
  auth, flag-gated only) so a plain `<a download>` works; zips the agent files in-memory + a per-OS
  INSTALL.txt → `cityagent-folder-sync-<os>.zip`. Modal buttons (`FolderSyncSetupModal.vue` osButtons) →
  `/api/sync/download/<os>` with `download` attr. Agent source is BAKED into the image at
  `/app/folder-sync-agent` (via docker cp + commit); endpoint falls back to a repo-relative path.
  Dockerfile COPYs `./folder-sync-agent → /app/folder-sync-agent` (after skills_library) so a clean build
  includes it; if that COPY is ever removed the download 503s (re-bake via docker cp + commit as a stopgap).
  No signed native installer yet (Phase 6) — zip ships the Python agent (pip + run).
- **E2E verified live** (org 55278108, flag ON, minted key): agents 200 → new push (created ds) → same file
  →`skipped` (delta) → edited file →`updated` (same ds reused, same-schema merge) → bind to CRM studio →
  StudioDataSource link created + `studio_id` returned → status grouped by machine. Test rows cleaned.

## Changelog / "What's new" (2026-06-25, BAKED)
Versioned feature feed surfaced as a 🔔 bell popover in TopNav (before profile).
- Source: `CHANGELOG_HYBRID.md` (repo root, `## v<semver> — <title>  (<date>)` + `-` bullets) +
  `VERSION_HYBRID` (current semver, now `1.2.0`). Separate from upstream `VERSION`/`CHANGELOG.md`.
- BE: `app/services/changelog.py` (parser, fail-soft) + `routes/changelog.py`
  (`GET /api/changelog`, `GET /api/changelog/unseen`, `POST /api/changelog/seen`) + per-user
  `users.last_seen_changelog` (mig `chlogseen1`). Registered in main.py.
- FE: `components/nav/WhatsNew.vue` (bell+badge+popover, Activity/What's new tabs, version chip,
  per-release cards) + `pages/changelog/index.vue` (See all). Wired into `nav/TopNav.vue`
  (explicit import, between New-Report and profile). RULE: every shipped feature bumps
  `VERSION_HYBRID` + adds a `CHANGELOG_HYBRID.md` entry.

**Current state (2026-06-28):** image `cityagent-analytics:dev` on `:3007` (baked `:v1.58.2`), branch `main`,
mig head **`connvis1`** (off agentconn1), `VERSION_HYBRID`=**1.58.2**. **GIT: v1.51→1.58 pushed `e92eb8c` (main); v1.58.1/.2 doc+fix EPHEMERAL, NOT yet pushed.**
**v1.56–1.58.2 = PROGRESS WAVE + DOCK + AUTO-ARTIFACT + OutputsFeed FIX — detail → DEVLOG/CHANGELOG 2026-06-28:**
- **v1.56–1.57 progress wave/dock:** flat "Thinking…" → warm clay `wave · live step · wave · m:ss` in the report chat. **Real renderer = `pages/reports/[id]/index.vue` inline header + bare-dots block** (NOT `AgentStepTimeline.vue` — that's a different surface; `runningStageText(m)` from `blocksToSteps`). `.cai-wave` CSS (4-hump path, scaleY 0.35–1.15, 1.3s, `cc-shimmer` text). Home idle wave (`pages/index.vue .home-wave`). Docked status strip above composer = **autoBuilding-phase ONLY** (v1.58.1 dropped the `runActive` branch — it duplicated the inline indicator).
- **v1.58.0 AUTO-ARTIFACT (`HYBRID_AUTO_ARTIFACT`, default OFF, ON org 1a073f60):** data turn with zero artifacts → background dashboard build. `services/auto_artifact.py schedule_auto_artifact()` → strong-ref'd `asyncio.create_task` → fresh session (reload by PK) → reuse `report_slides._generate_artifact(mode='page')`; idempotent (zero-artifact gate = 1 build/report), fail-soft. Hooks `completion_service.py` non-stream + stream after answer+sense_making. FE polls `/artifacts/report/{id}` 6s×30 (`autoBuilding`) + dock "Building a dashboard…". VERIFIED LIVE end-to-end (page:completed ~50s). Clarify turns (ambiguous ask, multiple active sources) run no create_data → no artifact = EXPECTED.
- **v1.58.2 BUG FIX (Outputs "No items yet" despite built artifacts):** ROOT CAUSE = both `ChatSummary` mounts (mobile L123 + desktop L1045) in `reports/[id]/index.vue` never passed `:messages` → `OutputsFeed` had 0 turns → empty state even with completed `page`/`slides` artifacts (artifacts render only inside turn blocks). FIX = `:messages="messages"` on both. ChatSummary already declared+forwarded the prop.
**v1.52–1.55.1 = CONNECTOR VISIBILITY + TABLE/SHARING UI + EDIT FIXES + AUTHZ HARDENING — detail → [[project_cityagent_connector_tiers]] (sections G–K) + DEVLOG/CHANGELOG 2026-06-28; pushed `e92eb8c`.** Headlines: v1.53 added `connections.visibility` enum private|shared|org (mig **connvis1**) + self-service `PATCH /connections/{id}/visibility`; v1.54 table UI (`ConnectorsTable.vue` + `ConnectorSharingPanel.vue`, default-private) on per-agent + org Connectors pages; v1.55 edit fixes (roomy `ConnectionDetailModal`, OWNER-OR-ADMIN `_guard_private_owner` super-admin override, Connectors nav open to all members); **v1.55.1 = authz hardening — `_guard_private_owner` wrapped as FastAPI dependency `guard_owned_connection`, wired `Depends(...)` into all 9 connector mutate/test/reindex/tools routes so a new route can't ship without the owner/admin check (RULE: new connector mutate route → add `_guarded=Depends(guard_owned_connection)`).** Below is the older v1.51 baseline (still applies):
**v1.51.0 = CONNECTORS INSIDE EACH AGENT (Activate for agent) — flag `HYBRID_AGENT_CONNECTORS` (already ON), reuses `StudioDataSource` pin model so NO new table/migration, EPHEMERAL (docker cp + restart + fe-sync), NOT baked/pushed.** Per-agent **Connectors page** in studio left rail (tab `connectors` already mounted in `pages/studios/[id]/index.vue` ~L2253/L1071 — no index.vue edit). FE `components/studio/StudioConnectors.vue` REWRITTEN: two tabs **My Connectors** (caller's private studio-bound connectors — create/edit/test/delete) / **Shared Connectors** (admin-configured, reusable); per-card **Activate for agent** ↔ **✓ Active · Deactivate** + sync date; "Add connector" modal creates+auto-activates a private connector; cards key off `conn.connection_id`. BE `routes/studio_sources.py`: `GET /studios/{id}/connectors` now returns `{mine, shared}` (`StudioConnectorListItem{connection_id,name,type,owner_user_id,is_org,active,data_source_id,sync_status,last_synced_at}`; shared visibility reuses connection.py `_conn_visible` — admin→all org connectors, member→granted/public-DS-backed, private-not-owned NEVER listed; `_pinned_ds_ids` → `active`). New `POST/DELETE /studios/{id}/connectors/{connection_id}/activate` (editor+): ensure a DataSource wraps the connector (reuse first, else create private DS w/ name-clash fallback) → pin/unpin `StudioDataSource` (dedupe + undelete) → `schedule_bootstrap_on_source_pin` sync. Added import `permission_resolver.resolve_permissions, FULL_ADMIN`. VERIFIED live (studio d4fb8a10): list `{mine:[], shared:[3]}` all inactive → activate SQLite Chinook → `active:true` → deactivate → `active:false`. LANDMINE: EPHEMERAL — new `studio_sources.py`+`StudioConnectors.vue` lost on force-recreate; bake must ship them with v1.50's connection model/guard/route + agentconn1. Detail → DEVLOG/CHANGELOG 2026-06-28 + [[project_cityagent_connector_tiers]]. **v1.50.0 = TWO-TIER CONNECTORS + MEMBER EMAIL REDACTION + AGENT-AS-PROXY (confirmed) — flags `HYBRID_AGENT_CONNECTORS`+`AGENT_ACL` already ON, manual DDL (`connections.owner_user_id`+`studio_id`), EPHEMERAL (docker cp + ONE restart + fe-sync), NOT baked/pushed.** THREE sharing models: (1) connector-grant (`resource_grants` user/group→connection, reuse `rbac.py` `/organizations/{org}/resource-grants` GET/POST/DELETE) → member SEES+reuses connector; (2) agent-as-proxy (share a STUDIO → member QUERIES via the studio's bound connection creds under `auth_policy=system_only` for ANY caller; `private_connector_guard.require_owner`/`filter_visible` guard ONLY the management plane, never `data_source_service.resolve_credentials_for_connection`; who-may-run=`AGENT_ACL`, whose-creds=`auth_policy` — NO code change, confirmed by trace); (3) personal connector (`ConnectionCreate.scope="personal"`→`owner_user_id=current_user.id` FORCED, any member; `scope="shared"`→admin-only owner NULL). `routes/connection.py` DROPPED blanket `@requires_permission('manage_connections')` on POST → manual scope branch; `_conn_visible` also keeps a member's OWN private connector; `owner_user_id` added to `ConnectionSchema` (3 build sites). Member PII: `routes/organization.py get_members` redacts non-admin viewers — `_mask_email` (`a***@domain`) + null note/auth_sources/invite/login/external on OTHER rows; own + admin (full_admin/manage_members/superuser) full. FE: `connectors.vue` two sections (Shared/My Connections) + open to all + admin "Manage access"; `AddConnectionModal` scope picker; `ConnectForm` `scope` prop; NEW `ManageConnectionAccessModal.vue` (user/group grant editor). VERIFIED live: member shared-create→403, personal→200 owner-forced, isolation (admin can't see member's private), grant flow (admin grant spreadsheet-1→rahul→visible), email mask. 🔴 **LANDMINE: agentconn1 NEVER BAKED** — running `ca-app` was MISSING `services/private_connector_guard.py` AND its `models/connection.py` lacked the owner cols (lost on prior force-recreate) → `/connections` 500'd for everyone; hot-cp'd both + ran column DDL. ALL EPHEMERAL — force-recreate wipes again until a proper bake runs migration agentconn1. Test residue org 1a073f60: `Rahul Personal Chinook` conn + spreadsheet-1→rahul grant + rahul pw reset `Rahul12345`. Detail → DEVLOG/CHANGELOG 2026-06-28 + [[project_cityagent_connector_tiers]]. **v1.49.0 = SLIDES BUILD-FIX + OUTPUTS Q/A FEED + SESSION SUMMARY + ARTIFACT-OPEN ROUTING — flag `session_summary` (org setting, default ON), ONE manual DDL (`ALTER TABLE reports ADD COLUMN session_summary json`), EPHEMERAL (docker cp + restart + fe-sync), NOT baked/pushed.** Five things, built via sub-agents. (A) **Slides actually build now.** ROOT CAUSE decks failed silently: `create_artifact` slides-mode LLM wrote python-pptx using `getattr()` (the prompt's OWN `style_chart_text` example used it twice → LLM copied verbatim) → sandbox AST gate (`code_execution.FORBIDDEN_BUILTINS` bans getattr/hasattr/setattr/eval/exec/open/...) rejected → `artifact.status='failed'`, no pptx/previews → Slides panel empty; chat STILL said "✅ created" (LLM text decoupled from exec result). FIX: hard SANDBOX-RULES header in slides prompt (use `'x' in dir(obj)`/try-except) + rewrote both example helpers getattr-free; HONEST failure — observation summary now says "Slide deck generation FAILED… do NOT claim success" + `observation.failed/status/error`, success wording gated on `status!='failed'`. Verified: a clean deck rebuilt `completed`. (B) **Outputs = per-turn Q/A/Decision feed** (`OutputsFeed.vue`): each turn = timestamp + ASKED question + ANSWER card + `DecisionCard` + artifact chips (status + Open/Retry); newest expanded, older collapsed; Q(user row)↔A+sense_making(system row) paired; artifacts mapped by recency. ChatSummary now takes `:messages`. (C) **SESSION SUMMARY** — pinned card atop Outputs synthesising ALL turns via ONE cheap haiku pass (`is_small=True`) → `{headline, decision, key_findings[], produced[], next_steps[]}`; `app/ai/knowledge/session_summary.py` (mirrors sense_maker, never raises) + GET/POST `/reports/{id}/session-summary` on report_slides.py + cached in NEW `reports.session_summary` JSON col (manual ALTER) with `generated_from` marker → FE `SessionSummaryCard.vue` (stale badge + Refresh, auto-builds once when empty+completed-turn). Flag `session_summary` org setting default ON. (D) **Slides panel honest states**: `hasGoodSlidesArtifact` requires `status==='completed'` (was `!=='failed'` → pending mounted empty frame); new `pendingSlides` → "Building your slide deck…"; `failedSlides` → failed card + **Retry**; refetch artifacts on run-end (failed builds never flip `hasArtifacts`); `generateSlideDeck` POLLS up to 4min for the finished deck (build ~120s > tool timeout 60s + HTTP patience → one-shot refetch missed it). (E) **Artifact-open routing**: `handleOpenArtifact` ROOT CAUSE hardcoded `rightPanelView='artifact'` (dashboard frame) for every artifact → slides opened the dashboard; now routes by `mode` (slides→'slides' view) AND when the clicked artifact isn't `completed` (chat card points at the failed id), selects the latest COMPLETED same-mode artifact instead of dispatching `artifact:select` on the broken one (which rendered blank). LANDMINES: (1) slides Explain/pptx is LLM-emitted — re-verify grounded. (2) session summary auto-build fires once/page-session; mobile ChatSummary mount lacks `:messages` so feed empty there (card still renders). (3) `reports.session_summary` col is manual DDL → survives restart, LOST on force-recreate until baked. (4) ONE `docker restart ca-app` for the cp'd backend (workers=4). Detail → DEVLOG/CHANGELOG 2026-06-28 + [[project_cityagent_explainable_dash]]. **v1.48.0 = EXPLAINABLE DASHBOARD + DECISION-IS-NO-SURPRISE + OUTPUTS LOADER + PICKER DEFAULTS AUTO — flag `dashboard_key_insights` (org setting, default ON), NO migration, EPHEMERAL (docker cp + restart + fe-sync), NOT baked, NOT pushed.** Four UI/AI upgrades. (A) **Explainable dashboard**: `create_artifact.py` page/React prompt (`_build_page_prompt`) now bakes — gated on `dashboard_key_insights` via `organization_settings.get_config(...)` (threaded from `runtime_ctx['settings']`, default-ON) — a top Decision callout (`DECISION · Watch/Act/Hold · confidence`) + Key Insights card (3–5 bullets, each must cite real number/site/period from the build-time viz/observation data) ABOVE the KPI row, plus **per-widget Explain** on every KPICard/SectionCard = collapsible `<details>` with up to 4 tiers Reading/Why/So-what/Do (descriptive→diagnostic→prescriptive, beyond Power-BI) + WATCH badge on anomaly widgets; grounding rules non-negotiable (cite-only-real, fewer-true-beats-guessed). Render path = native `<details>` JSX (the existing `InfoPopover`/`viz` prop only has Data/Code tabs, no prose slot). Independent of sense_making timing (root cause: dashboards build mid-run, sense_making is post-run → old `decision_banner_block` was always empty; kept as bonus). NOTE: my earlier same-day edit to `create_dashboard.py` (semantic-grid builder) was the WRONG builder — real dashboards = `create_artifact` page React; that edit is harmless/dormant. (B) **Decision no surprise + composer lock**: `completion_service.py` streaming path emits NEW SSE `sense_making.pending` right before `build_sense_making` (existing `completion.finished` = ready/unlock). FE `index.vue` `decisionPending` ref: `sense_making.pending`→true, `finished`/error/abort/`[DONE]`→false (FAIL-OPEN — never locks if event absent); drives pending shimmer DECISION card in chat+Outputs ("Reading the result… forming a decision") + locks composer (`PromptBoxV2.canSubmit` adds `&& !props.decisionPending` + inline "forming the decision…" note). (C) **Outputs loader**: `ChatSummary.vue` shows `<DashboardSkeleton mode="page" />` while `runActive` (`generating` prop from `index.vue`, both mounts) until answer/decision lands. (D) **Picker defaults to Auto**: `PromptBoxV2.loadModels` defaults `selectedModel='auto'` when nothing persisted (loads auto-flag first); saved/explicit model preserved; other options untouched. LANDMINES: (1) `create_artifact` page-mode Explain is LLM-emitted JSX — verify it actually renders grounded `<details>`, not generic. (2) pending-lock is belt-and-suspenders — during the window the stream is open so composer already shows Stop (Send not rendered); visible change = inline note + pending card. (3) two backend files hot-cp'd + ONE `docker restart ca-app` (workers=4). Detail → DEVLOG/CHANGELOG 2026-06-28 + [[project_cityagent_analytics]]. **v1.47.0 = AUTO MODEL SELECTION — flag `HYBRID_AUTO_MODEL` (default OFF, ON org `1a073f60`), NO migration, EPHEMERAL (docker cp + fe-sync), NOT baked, NOT pushed.** Model picker gains an **"Auto"** option (sentinel `model_id="auto"`) → `app/ai/knowledge/auto_model.py` complexity classifier (deterministic 0..1 score → Fast/Balanced/Reason → cheapest capable of the org's enabled models; ONE cheap LLM tie-break only in fuzzy band [0.40,0.60]; NEVER raises → org default). Hooked at 3 model-resolution sites in `completion_service.py` (estimate skips classifier); decision persisted to `completion.auto_model` + emitted LIVE as `auto_model` SSE at stream start + v2 top-level field. FE: Auto picker option + live `⚡ Auto → <Model>` chip + "Auto · <Model>" label + Outputs "routed to" pill. LANDMINE: flag-enable needs ONE `docker restart ca-app` (workers=4); two `messages.value` maps differ in indent (tabs vs spaces). Detail → [[project_cityagent_automodel]] + DEVLOG/CHANGELOG 2026-06-28. **v1.46.0 = SAFE-ENABLE WAVE + LIGHTWEIGHT FORECASTING + PER-AGENT SELF-LEARNING — image `d5399fbdbea5`, NO migration, NOT git-pushed.** Enabled the stable hybrid set on org `1a073f60` via DB overrides (62 effective): Wave A (governance/column-intel/compliance/file-browser/agent-connectors) + Wave B (oneclick-artifacts/rich-email/agent-reports/automap/bitemporal/join-graph/quotas/workflows) + safe experimental (context-compact/brain-graph/skill-autogrow/skill-optimize) + cheap daemons (join-mine + studio-learn). Held (cost/risk): ambiguity-gate, autotrain-on-index, pack-autobind, federation (no S3), costly daemons. **Forecast → statsmodels** (`forecast.py` Prophet→`ExponentialSmoothing` seasonal/trend/linear cascade + ±1.96σ band + fail-soft LLM narrative from `runtime_ctx['model']`; `requirements_versioned.txt` `prophet`→`statsmodels==0.14.2`+`patsy`, 10MB not 200MB; flag meta `needs_dep`→`stable`). **Per-agent self-learning** = `studio.config['self_learn']{enabled,cadence(6h|daily|weekly|monthly|off),hour_utc,last_run_at}` (no migration) + NEW `routes/studio_self_learn.py` GET/PUT (owner/editor) + `schemas/self_learn_schema.py` + FE `components/studio/StudioSelfLearn.vue` (Autopilot tab); `studio_learn_daemon.py` rewritten override-aware (`flags.STUDIO_LEARN_DAEMON` — fixed UI toggle being IGNORED) + per-studio `is_due()` cadence + hourly tick + stamps `last_run_at`; `flags.STUDIO_LEARN_DAEMON` property+snapshot; 12/12 cadence tests. Dead toggle `HYBRID_CONTEXT_COMPACT_LLM` (TODO stub) → `HIDDEN_FLAGS` (69 visible). Self-tested local w/ real LLM (forecast ETS+narrative, oneclick dashboard `completed`, compliance/column/workbook). **LANDMINES: (1) `ca-app` `--workers 4` → PUT `set_override` patches ONE worker; every enable wave needs ONE `docker restart ca-app` to converge from DB. (2) daemons that read `os.environ` direct (studio-learn did) ignore the UI override → read `flags.X`. (3) host `main.py` AHEAD of image → `studio_reports.py`+`report_slides.py`+`connection_files.py` were hot-cp-only/missing from image → cp host main.py = ImportError loop until all re-cp'd (now baked). (4) statsmodels pip-installed in container survives restart, LOST on force-recreate until baked.** Prod box 13.251.74.176 still needs this image/files. Full detail [[project_cityagent_analytics]] + DEVLOG 2026-06-27. **v1.45.0 = UI FIRST-RUN SETUP + CONNECTOR ORG AUTO-JOIN + OPENROUTER-FROM-UI — image `b73a9df22e87`, NO migration, NO flag, NOT committed.** Three permanent fresh-install fixes. (A) Zero-user install shows a "Create super-admin" form on `pages/users/sign-in.vue` (same clay page), gated by `needs_setup`=`user_count==0` on `GET /api/settings` (**FAIL-CLOSED**: count error→False→login, never signup); `createAdmin()` POSTs `/api/auth/register`; `auth.py on_after_register` elevates the first user (`users==1&orgs==0`) to `is_superuser`; signup locks after user#1 → screen never returns. Env-free (but `docker-compose.build.yaml` now ALSO passes `DASH_ADMIN_*` through for the headless seed path — compose only used `.env` for `${VAR}` interp, never injected → original prod login-400). (B) ALL external connectors (LDAP/Google/MS/Keycloak/SSO) auto-join the PRIMARY org via NEW `auth.py _ensure_user_in_org(email)` at **6 hooks** (LDAP existing+new, oauth_callback returning+linked+new) — kills the post-login "Create Organization" dump; `Membership(role='member')`+system RoleAssignment, idempotent, fail-soft, rescues orphans on next login. (C) Set the OpenRouter key from Settings→LLM and the 5 seeded models light up: `services/llm_service.py create_provider` now UPSERTS via `_find_upsert_target` (matches the shipped provider across the **openrouter↔custom family** by base_url) + `_apply_key_and_models_to_existing` (set key, add only new model_ids, `_enable_preset_models` on blank→set) — fixes the duplicate/409 that left the preset models keyless (the `"No cookie auth credentials found"` 401); `update_provider` preset-block removed; keys stay DB-only Fernet, FE unchanged. Fresh-install test harness `scratchpad/docker-compose.test.yaml` (`-p catest`, :3017). **LANDMINES: FE OpenRouter card type=`openrouter` but seed=`custom` → matcher must span both; create→update delegation breaks (`_update_models` wants `.id` objects, create sends dicts) → use the `_create_models` dict path; seed encrypts BLANK key so `api_key<>''` SQL is NOT a blank-check, only decrypt is.** Prod box 13.251.74.176 still needs this image/files. Full detail [[project_cityagent_analytics]] + DEVLOG 2026-06-27. **v1.44.0 = PERSONAL GROUPS (My Groups) — image `20316475`, rollback `pre144-rollback`, flag `HYBRID_USER_GROUPS` (ON for org 1a073f60), NO alembic migration but ONE manual DDL.** Any member creates personal contact groups: `routes/me_groups.py` (`/api/me/groups` CRUD + `/api/me/contacts`) + `services/me_groups_service.py`, gated `flags.USER_GROUPS` (404 off). Personal group = `Group` row with `owner_user_id` set; every query scoped `owner_user_id == current_user.id` (can't touch org/admin/LDAP groups); creator auto-added; unique name org-wide via existing `UNIQUE(organization_id,name)` → 409. FE: NEW `pages/settings/my-groups.vue` (full CRUD, DEFAULT layout — visible to ALL via no-permission nav item in `composables/useAppNav.ts`, NOT the permission-gated Settings rail); `StudioAccessPicker.loadGroups` merges `/me/groups` (badge "mine") + admin `/organizations/{org}/groups` (skipped on 403 for non-admins); `StudioCreateGroup` now POSTs `/me/groups` + members from `/me/contacts` (kills old 402/403 on admin org-groups route). **DB LANDMINE: prod `groups` table lacked `owner_user_id` (model had it, never migrated) → manual `ALTER TABLE groups ADD COLUMN owner_user_id varchar(36) REFERENCES users(id)` + index.** **DEPLOY LANDMINE: running image `main.py` predated the me_groups route files → restore IMAGE `main.py` (`docker create`+`cp`) and surgically add only the `me_groups` import + `include_router`; do NOT cp host `main.py` (host is ahead, imports `studio_reports` etc. absent in image → boot ImportError loop).** v1.43.0 = USER PROVENANCE + super-admin-only user creation + email-merge hardening (image `0b2b275d`, rollback pre143-rollback, NO migration/flag, 4 parallel subagents). Identity keyed by EMAIL = one `users` row multi-credential (local pw + `ldap_dn` + `oauth_accounts[]` + `scim_external_id`); SSO `oauth_callback` LINKS by email, LDAP find-or-provision by email → local+LDAP+SSO same email AUTO-MERGE into one id. Members table Source badge via NEW `MembershipSchema.auth_sources` (`_derive_auth_sources` in routes/organization.py: ldap/sso:<provider>/scim/else local; get_members re-queries `selectinload(User.oauth_accounts)` + sets on pydantic schemas). Manual create LOCKED: `add_member`+`create_user_directly` add `is_superuser` 403 (FE hides Add Member+Import unless session `is_superuser`); LDAP/SSO auto-provision untouched. GroupsManager Source badge from `Group.external_provider` (synced groups disable member edit). NEW env `OAUTH_TRUST_EMAIL` default TRUE (no regression); false→refuse SSO email-link unless verified. OpenWebUI parity = their opt-in `OAUTH_MERGE_ACCOUNTS_BY_EMAIL`. v1.42–1.42.1 = GROUP access [share studio→group] + custom_roles un-gate (license.py + useEnterprise.ts BOTH).**
**v1.42.0 = GROUP-based agent access + merged Access tab.
Share a studio to a GROUP (incl. AD/LDAP-synced) → every member auto-sees it in studios list + chat dropdown.
Flag **HYBRID_GROUP_ACCESS** (default OFF; org `1a073f60` now has **9** overrides). NO migration — reuses
`ResourceGrant`(`resource_type='studio'`,`principal_type='group'`,`permissions` JSON). Backend `studio_access.py`
(`group_granted_studio_roles`+`user_group_ids`, resolver step 2.5 write→editor/read→viewer, **`GET /studios` query
OR-includes group-granted ids** = the auto-appear mechanism, both list+`AgentSelector` source `/studios`) + routes
`GET/POST/DELETE /studios/{id}/group-grants`. FE: merged `members` tab INTO `access` (`?tab=members`→access, Delete
in `StudioAccess.vue`); Private/Public toggle (Link=advanced); Groups list + `StudioAccessPicker.vue` (AD-badge,
member counts, Viewer/Editor, `POST /enterprise/ldap/sync`). LANDMINE: `ResourceGrant` col is **`permissions`**
(JSON list), NOT scalar `permission`. P5 inline create-group deferred (toasts pointer). Reuses existing
`ee/ldap/sync_service.py`+`ee/oidc/group_sync_service.py`+RBAC group CRUD — ~70% pre-built; ONLY gap was studio
resolver/list never checking groups. Rollback `pre142-rollback`.**
**v1.41.0 = live studio Training-log (Claude-Code CLI
terminal: per-stage ▸ markers + model/tokens/errors, Logs⇄Steps toggle, Reset/Retry; `train_orchestrator` log[]
buffer + `_RunLogHandler` + `POST /studios/{id}/train/reset`) + AI column meanings (closes gap: nothing wrote
`SemanticColumn.meaning`; new `propose_column_meanings` + `POST /knowledge/ai-suggest-columns/{ds}` gated
SEMANTIC_LAYER + folded into Auto-train semantic_metrics stage auto-approved) + Infographic/InsightMap → SOON.
EPHEMERAL (docker cp + `docker commit`, NOT Dockerfile build). Org `1a073f60` got 8 hybrid_overrides (Intel
flags ON, FORECAST off=needs prophet). Rollback tags `pre140-rollback`/`pre141-rollback`, backups in scratchpad.**
**v1.40.0 = cosmetic chat redesign (Claude/ChatGPT
grammar: collapsible thinking, threaded tool steps, warm `#FAF8F3` canvas incl Outputs pane) + CreateDataTool
no-garble count chip + `awaitingClarify` paused-chip + fresh-DB `create_report` stale-`studio_id` FK guard.
Cosmetic-only, no agent-loop change. EPHEMERAL (FE `yarn generate`+docker cp, backend docker cp+restart) —
NOT baked. Rollback backups in session scratchpad `rollback_phaseA/`.** **v1.37.0 = per-agent scheduled reports + universal
report-delivery (pushed `a5444ab`). v1.38–1.39 = one-click artifacts (flag `HYBRID_ONECLICK_ARTIFACTS`, ON org
55278108): empty report panels become builders — `Generate slide deck` (real python-pptx deck), `Generate
dashboard` (page artifact), and Excel auto-fills via read-only `GET /api/reports/{id}/workbook`. BE
`routes/report_slides.py` (shared `_generate_artifact(mode)` reuses the chat `create_artifact` pipeline);
fixed two pre-existing slides bugs (pptx AST gate forbade `getattr` → `PPTX_ALLOWED_BUILTINS`; empty-category
charts crash → slides-prompt DATA SAFETY rule). v1.38–1.39 EPHEMERAL (`docker cp` + `fe-sync`, NOT baked, NOT
pushed).** Earlier source-only stack (v1.31.0–1.33.1) still applies. Pre-1.28 local backlog still applies. v1.22
= full warm-theme sweep (every page + 148 comps). **v1.23.0 BAKED** = Parquet result storage +
interactive query endpoint (flag `HYBRID_PARQUET_RESULTS` **default ON**) — large step results
(≥`HYBRID_PARQUET_MIN_ROWS`=2000 rows) offload to compressed Parquet on `ca_uploads`; dashboards
push filter/sort/agg to DuckDB via `POST /steps/{id}/query` (allow-listed, no raw SQL). See
`docs/parquet-results.md`. `scripts/safe-upgrade.sh` = guarded bake (backup DB+uploads, health-gate,
auto-rollback).

**v1.25–1.27 (BAKED + live):**
- **v1.25.0 plain-language "What's new":** `CHANGELOG_HYBRID.md` IS the user-facing popover source,
  so it must read plain. Parser `backend/app/services/changelog.py` now splits bullets — **top-level
  `- `** → `features` (user-facing, shown in `WhatsNew.vue` popover, render plain, NO markdown/paths/
  jargon), **indented `  - `** → `details` (technical, hidden from popover, collapsed `<details>`
  toggle on `/changelog` page only). Recent entries rewritten plain. RULE going forward: write
  top-level bullets as plain user copy, push file paths/flags/internals to indented detail bullets.
- **v1.26.0 Channels global-vs-custom:** per-platform mode radio in `StudioChannels.vue` ("Use
  organization default" vs "Custom for this agent") mirroring the Email tab. Mode DERIVED from data
  (per-studio channel row = custom; none = org default) + local override to flip before a row exists;
  global branch shows org-default note + "Remove custom" revert. Mode-aware status chip. Replaced the
  old "🔒 Locked" banner with a data-scope note. **NO backend change** — reuses NULL studio_id → org
  fallback.
- **v1.27.0 equal card buttons:** Decks (`pages/presentations/index.vue`) labels shortened
  (Open & generate→Generate, Open in chat→Chat) + `whitespace-nowrap`+`box-border`+`min-w-0` so the
  `grid-cols-2` buttons stay flat + equal. Dashboards/Home (`components/home/RecentReportCard.vue`)
  button CSS `flex:1 1 0; width:0; box-sizing:border-box; white-space:nowrap` — bordered ghost +
  borderless primary now render identical width.

**v1.28–1.30.2 Identity Provider + LDAP overhaul (v1.30.1 BAKED; v1.30.2 source-only):**
- **v1.28.0 login shows only enabled providers:** `pages/users/sign-in.vue` per-button `v-if` on enabled
  state; `/api/settings` exposes `ldap_enabled` (+ later `ldap_logo`). Google/Microsoft/Keycloak come
  via `oidc_providers` (MS+Keycloak stored AS oidc providers, names microsoft/keycloak).
- **v1.29.0 IdP brand logos + toggles + provider library:** `utils/idpLogos.ts` (preset brand SVGs +
  `idpLogoSvg`), `utils/idpTemplates.ts` (`IDP_TEMPLATES`), `components/idp/IdpLogoPicker.vue`,
  `IdpProviderLibraryModal.vue`. `identity-provider.vue` rows = `ssoRows` computed (Google·Microsoft·
  Okta·Keycloak defaults·custom OIDC) w/ logo + smart 4-state pill (`pillText`/`pillClass`) + inline
  quick-toggle (saves immediately) + "Add provider" library. Logo picker in every config modal.
  Backend `logo:str` on Google/OIDC/LDAP (`_clean_logo`=preset key OR data:image ≤400KB, fail-soft "").
  SCIM has no config object → no logo.
- **v1.29.1 LDAP LOGIN FIX (root cause):** login `core/auth.py` read FILE config `settings.dash_config.ldap`
  while the admin UI saves LDAP to DB `OrganizationSettings.config['ldap']` → UI LDAP IGNORED at login
  (Test worked, login didn't). Fix: `get_effective_ldap_config()` (DB-over-file, own session);
  `UserManager._do_authenticate`/`_ldap_authenticate` use it. `_build_server` derives use_ssl from URL
  scheme (no SSL toggle in UI).
- **v1.30.0 MULTIPLE LDAP directories + username login:** storage `config['ldap_directories']` (list;
  legacy single `config['ldap']` auto-migrates to id="default"). Backend `find_user_by_username`
  ({username} filter, `escape_filter_chars`) = DocSensei-style USERNAME login (not email-only);
  `get_effective_ldap_directories()`; login ITERATES all enabled dirs (username-first → email fallback →
  first success wins → all-unreachable → local break-glass; binds with the dir's email). Routes
  **`/api/enterprise/ldap/directories[/{id}][/test]`** (GET/POST/PUT/DELETE/POST-test) on `ldap_admin_router`
  (prefix `/enterprise/ldap`, mounted `main.py` `enterprise_router` prefix `/api`; EE-gated +
  manage_identity_providers). Pw Fernet, never returned (`bind_password_set`). FE
  `components/idp/LdapDirectoriesPanel.vue` (multi-dir list: row toggle/test/configure/delete + "Add
  LDAP / AD directory") + `LdapDirectoryModal.vue` (DocSensei default fields: name/host/port/bind DN/
  bind pw/base DN/user filter {username}/email+name attr; Advanced collapsed = ssl/tls/group sync/etc).
  Replaced the single-LDAP row+modal in identity-provider.vue. Built by 2 parallel agents.
- **v1.30.1 removed floating robot:** dropped `<RobotAssistant />` (app.vue) + `<AgentThinking />`
  (layouts/default.vue) — gone from all screens. Components kept, just unmounted.
- **v1.30.2 LDAP panel render fix (NOT baked):** LANDMINE — Nuxt auto-imports `components/idp/*` with an
  **`Idp` prefix**, so `LdapDirectoriesPanel.vue`/`LdapDirectoryModal.vue` registered as
  `IdpLdapDirectoriesPanel`/`IdpLdapDirectoryModal`; bare `<LdapDirectoriesPanel>`/`<LdapDirectoryModal>`
  tags resolved to nothing → panel invisible. (`IdpLogoPicker` worked only because its filename already
  starts with `Idp`.) FIX = EXPLICIT imports in `identity-provider.vue` + `LdapDirectoriesPanel.vue`.
  RULE: any component under `components/<dir>/` whose filename doesn't start with `<Dir>` must be
  explicitly imported (or referenced with the dir-prefixed name). User stopped the bake — pending.

**v1.24.0 Per-agent Channels + Email/SMTP + Docker build speedups (BAKED + live):**
- **Channels** + **Email / SMTP** are now their OWN left-rail tabs in the Studio MANAGE group
  (split from the old combined "Access & Channels"): rail = Settings · Access & Members · Channels ·
  Email / SMTP · Members & Share.
- **Channels tab** (`components/studio/StudioChannels.vue`) — org-style **two-pane picker**
  (platform list + detail pane, status dots, set-up/reconfigure/enable/disable/delete). Reuses the
  existing Slack/Teams/WhatsApp/AI-Mailbox config modals + Telegram/MCP inline; same config method,
  org layout. Channels code REMOVED from `StudioAccess.vue` (now "Access & Members" = who/model/
  members/connections only).
- **Email / SMTP tab** (`components/studio/StudioEmail.vue`) — per-agent outbound mail: mode radio
  **global default** (inherit, zero-config) OR **custom SMTP for this agent**. Custom fields mirror
  org SMTP (host/port/security/user/pass/from/validate-certs) + connection test. Stored in
  `Studio.config['smtp']` (Fernet `password_enc`, no migration; `mode` key gates it).
  - Backend resolver `email_client_resolver.py`: new **per-agent SMTP tier** wins over org/global —
    `get_studio_smtp(db, studio_id)` (only when `mode=='custom'`+host), `_studio_smtp_resolved`,
    `choose_outbound(..., studio_smtp=)`, `resolve_outbound(..., studio_id=)`. `studio_id` threaded
    through `notification_service` (dispatch + send_custom_email + _resolved_send), report-share
    (`report.py`, now passes db+org+studio_id → org-SMTP now applies to shares too), and channel
    replies (`email_send_service.py`, `studio_id=report.studio_id`). NULL studio / global mode =
    byte-identical old behavior.
  - Routes `GET/PUT/POST-test /api/studios/{id}/smtp` in `external_platform.py` (flag
    `HYBRID_AGENT_CHANNELS`, owner/editor via `_require_channel_manager`). `StudioSmtpSchema`/
    `StudioSmtpUpdate` mirror `OrgSmtp*`. Verified live: precedence=studio_smtp, routes registered.
- **Dockerfile speedups** — dropped non-deterministic `apt-get upgrade -y` from backend +
  frontend builder stages (pin to base image = cache-stable; runtime `base` keeps its security
  upgrade); added BuildKit cache mounts on `yarn generate`
  (`node_modules/.cache` + `node_modules/.vite`, `sharing=locked`) → warm vite cache makes repeat
  FE rebuilds much faster (v1.24 FE rebuild hit "exporting layers" in seconds vs cold ~4min).
  NOT caching `.nuxt` (stale-module risk). Bake = slow only because `nuxt generate` is inherently
  minutes on first/cold; backend-only changes skip it (FE stage cache-hits).

**v1.20 Nav rail + v1.21 Settings restyle (BAKED):** killed the top-nav **dropdowns**
(Workspace/Build/Manage/Settings). Top items now route directly to the group's first page; a contextual
**left rail** (`components/nav/AppRail.vue`) shows ONLY the active group's items (one group at a time, like
the Skills sub-rail). Nav model extracted to shared composable `composables/useAppNav.ts` (single source for
TopNav + AppRail — `visibleGroups`/`activeGroup`/`isRouteActive`/`firstHref`/`showMcpModal`; module-level
singleton refs OK since SPA/`nuxt generate`). AppRail mounted in `layouts/default.vue` non-report branch
(`<div class="flex"><AppRail/><div class="flex-1 overflow-y-auto"><slot/></div></div>`); self-hides when
`activeGroup` is null (Home, Agent Studios [direct, excluded], detail pages w/ own rail). Studio-detail tabs
persist in URL (`?tab=`). **Warm-theme restyle (token-only migration, NO icon/logo/logic changes — applied
via per-file perl: `#C2683F`→`#C2541E`, `#A8542F`→`#A8330F`, `#E7E5DD`→`#E9E0D3`, `bg-[#FBFAF6]`→`bg-[#F6F1EA]`,
`bg-[#F4F1EA]`→`bg-[#F4EEE5]`, `bg-[#F3E7DF]`→`bg-[#FBEFE4]`, `ui-serif,Georgia[,'Times New Roman'],serif`
→`'Spectral',...`, h1 `text-2xl font-semibold text-[#1f2328]`→`text-[32px] font-medium text-[#211B14]`):**
Workspace Templates (full design rewrite); Build×5 (Knowledge/Instructions[ConsoleInstructions]/Queries/Skills/Memory);
Manage×3 (Connectors/Evals/Workflows); Settings×11 + `layouts/settings.vue` + FolderSyncPanel + Email/WhatsApp/Teams/Slack
integration modals. DESIGN MOCKS at `~/Downloads/login-screen-redesign-request/project/*.dc.html`
(Studios/Home/Workspace/Build/Manage/Settings v2). Pending: Workspace Reports/Dashboards/Presentations/Spreadsheets/Scheduled
+ Monitoring (own `layout: 'monitoring'` console, sits outside AppRail).
LANDMINE: pages with their OWN sub-rail (Skills category rail, Knowledge) show TWO rails (group rail + page rail) — acceptable.
LANDMINE: stack runs on **`docker-compose.build.yaml`** (ca-app/ca-postgres/ca-redis, vol `ca_postgres_data`).
NEVER recreate via plain `docker-compose.yaml` — different project (dash-* names, vol `postgres_data`) = fresh empty DB.

**v1.17–1.18 Claude Design rollout (FE restyle, BAKED, see DEVLOG):** warm palette app-wide
(bg `#F6F1EA`, accent `#C2541E`/`#A8330F`, Spectral + Hanken via `useHead` from TopNav). Login
(v1.17) + Studios/Home/Nav/Reports + new floating **AgentThinking** status widget
(`components/agent/AgentThinking.vue`, global in `layouts/default.vue`, REAL counts from
`/data_sources`+`/llm/models`, no fakes) (v1.18). TopNav now full-width (no `max-w` centering).
Report scope = segmented tab; report cards keep REAL `thumbnail_url` preview. Studio **detail** page
also rethemed warm. **FIXED studio-Open crash** (`reading 'name' of null` on REFRESH): teleported
`FolderSyncSetupModal`/`FolderSyncCard` read `studio.name` in a separate reactive scope during the
cold-load null window → `v-if="studio"` + `studio?.name`. LANDMINE: teleported modal/popover props
that read a fetched ref are NOT covered by the parent's `v-else-if="data"` guard — `?.`-guard them.
New `scripts/fe-sync.sh` = host `nuxt generate` + `docker cp`→ca-app dist (no rebuild, EPHEMERAL).
Local admin reset to `admin@cityagent.io`/`Admin12345` (fastapi-users = **argon2id**, not bcrypt).

**v1.13–1.15 (2026-06-25):**
- **v1.13.0** super-admin DIRECT user create (no invite): `POST /api/organizations/{id}/members/create-user`
  (admin-gated) + Members "Add user" modal. LANDMINE: do NOT route through `manager.create()` — its
  `_validate_user_creation` gate 400s non-first signups ("Sign-up is disabled"); insert the User directly
  (`PasswordHelper().hash` + is_active/is_verified) like the OAuth path, then add Membership. Also added the full
  `HYBRID_*` env block to `docker-compose.nginx.yaml` (it had NONE → every flag defaulted OFF, Studios locked) with
  visible features ON + a `redis` service.
- **v1.13.1** dashboard fullscreen black-charts fix: `ArtifactFrame` renders a 2nd iframe; `sendDataToIframe()` only
  posted to the bg iframe → fullscreen got no `ARTIFACT_DATA`. Now broadcasts to both + re-send on its load.
- **v1.13.2** see v1.13.0 LANDMINE (the direct-insert fix).
- **v1.14.0** ALL 65 hybrid flags toggleable in **Settings → Features** (was ~32). Extended `UPGRADE_FLAGS` with
  `category`/`status`/`note` for every flag + grouped/searchable UI + confirm dialog on risky enables. `_effective()`
  in `routes/organization_settings.py` falls back to override-or-env for the env-only daemon knobs
  (`EVAL_SCHEDULE_ENABLED`/`JOIN_MINE_ENABLED`/`STUDIO_LEARN_DAEMON_ENABLED` have no `flags` property). LANDMINE
  reconfirmed: a flag absent from `UPGRADE_FLAGS` is invisible in the UI AND its PUT 400s.
- **v1.15.0** Hybrid Search (`HYBRID_SEMANTIC_SEARCH`) is now REAL. **OpenRouter SUPPORTS embeddings** via its
  OpenAI-compatible `/embeddings` — `openai/text-embedding-3-small` (1536d = matches the existing
  `knowledge_search_index.embedding vector(1536)` column, NO migration), reusing the org's existing OpenRouter key.
  New `app/ai/knowledge/embeddings.py` (AsyncOpenAI, batched, fail-soft) + `indexer.py` (`reindex_org` from approved
  semantic/metrics/queries/docs → tsv + vectors); `hybrid_search.py` gained a pgvector cosine arm + 3-way RRF;
  `HybridSearchContextBuilder`+section wired into `context_hub` (gather tail) + `agent_v2` (gated). Routes
  `POST /api/knowledge/reindex` + `GET /api/knowledge/search-index/status`; Rebuild-index button on the Features
  Hybrid-Search row. Proven live (293 indexed+embedded, OpenRouter 200, relevant RRF hits). Optional reranker NOT
  added (RRF deemed enough; bolt-on later via OpenRouter rerank if needed).

**v1.11.0 One-command deploy + env super-admin:** (1) DEPLOY FIX: `Dockerfile` was `FROM cityagent-base:dev`
(local-only image from `Dockerfile.base`, never in a registry) → clean prod `docker compose up --build`
failed "pull access denied". FIXED by folding base into main Dockerfile as internal stage `FROM ubuntu:24.04 AS base`
(byte-for-byte Dockerfile.base content: MS ODBC/FreeTDS/libreoffice/poppler/playwright-deps + app user) +
final stage `FROM base`. Stages now: backend-builder, qvd2parquet-builder, frontend-builder, base, final.
`Dockerfile.base`+`scripts/build.sh` kept as optional fast-dev path. New `deploy.sh` (bootstrap .env→warn key→
compose up). (2) ENV SUPER-ADMIN: no global-superadmin existed (model=first registered user→org owner via
auth.py:715 `user_count==0` + `_ensure_org_for_first_uninvited_user`); sign-up link removed v1.8.0 so fresh box
was stuck. NEW `backend/scripts/seed_admin.py` (async, idempotent, fail-soft) run ONCE in `start.sh` after
alembic before uvicorn: reads DASH_ADMIN_EMAIL/PASSWORD/NAME, skips if unset OR email exists, else creates via
real user-manager (`get_user_db`→`get_user_manager`→`manager.create(UserCreate, safe=False)` → fires
on_after_register→org+owner) then fresh-session sets is_active/is_verified/is_superuser=True. Imports:
`app.dependencies.async_session_maker`/`get_user_db`, `app.core.auth.get_user_manager`,
`app.schemas.user_schema.UserCreate` (name min_length 3). Vars in docker-compose.yaml app env + .env.example.
PROVEN live: no-env→skip, existing-email→"already exists skipping". Baked. LANDMINE: seeder gates on email-exists
NOT user_count==0 — a NEW email on a populated DB would create a non-first user (no bootstrap org); intended use =
fresh deploy only.

**v1.10.0 Per-agent access control + Telegram channels:** an agent = a `Studio`. New flags
`HYBRID_AGENT_ACL` + `HYBRID_AGENT_CHANNELS` (`hybrid_flags.py`, default OFF, ON org 55278108).
(1) ACL: chat-time enforcement in `completion_service.py` — if `flags.AGENT_ACL` and
`report.studio_id`, calls `resolve_studio_access` (studio_access.py); None→403. Applied to BOTH
non-stream + stream completion paths (NOT the token-estimate path). Most ACL primitives already
existed: `Studio.share_scope` (private/org/link), `StudioMember`, member CRUD + `/share` routes.
(2) Per-agent model override: precedence request `prompt.model_id` > `studio.config['model_id']` >
org default (same 2 paths, flag-gated). (3) Telegram: mig `agentchan1` adds `studio_id`+`audience`
to `external_platforms`; routes in `external_platform.py` (`POST/GET/enable/disable/DELETE
/api/studios/{id}/channels[/telegram]`) + public inbound `telegram_webhook.py`
(`POST /api/ext/telegram/{studio_id}/webhook`, registered in `main.py`). Reuses ExternalPlatform
encrypt/decrypt_credentials, ExternalUserMapping verification (24h token), ReportService.create_report,
CompletionService.create_completion (foreground, reads back final answer), `telegram_send` via httpx.
Audience members(verify) | anyone(runs as owner). Webhook ALWAYS returns 200 {ok:true} (Telegram
no-retry). UI: `StudioAccess.vue` "Access & Channels" tab in `studios/[id]/index.vue` (who-can-use
radios, members, model dropdown, channels list + Telegram add modal); uses `useMyFetch`, fails soft
on 404. Members GET shape = existing `{id,user_id,role,user_name,user_email}` (NOT email/name).
LANDMINE v1: Telegram reply is SYNC foreground completion (slow agents may exceed webhook timeout —
v2 needs background + adapter). LANDMINE: `/verify/{token}` FE page not built (verify loop open).
LANDMINE: `/app/frontend/dist` owned by ROOT — `docker cp` needs `docker exec -u 0` rm + chown app:app.

**v1.9.0 Default OpenRouter LLM + .env.example:** new orgs auto-seed an OpenRouter
provider (current models: claude-sonnet-4.6 DEFAULT, claude-haiku-4.5 SMALL, claude-opus-4.8,
gpt-5.4-mini, gemini-2.5-flash) via the existing `set_default_models_from_config` org-create hook
(`llm_service.py`), driven by a `default_llm:` block in `dash-config.yaml` + `configs/dash-config.dev.yaml`.
Config `LLMProvider` schema (`dash_config.py`) extended: `api_key` defaults `""`, new `is_preset`
(default True) and `additional_config`. Seeded provider is **custom** type (base_url
https://openrouter.ai/api/v1, verify_ssl), **is_preset:false** so the key is editable from the UI
(Settings→Models) — key left BLANK (never in repo). LANDMINE: native `openrouter` + custom both
`decrypt_credentials()` unconditionally at LLM init (`llm.py:60`) → a NULL key CRASHES; seeder always
`encrypt_credentials("", "")` so blank → valid blob → "" → client builds, 401 until key set. Existing
org 55278108 untouched (already configured). Added root `.env.example` (placeholders only; `!.env.example`
allow-rule in gitignore; OpenRouter key is UI-set not env). LANDMINE: `docker cp` onto the bind-mounted
`/app/dash-config.yaml` fails "device busy" AND leaves a truncated stale view (macOS file-share cache) —
edit the repo file + `docker restart` to refresh; never cp over it.
Folder Sync (desktop folder auto-ingest, per-agent bind, delta upsert; flag ON org 55278108; E2E proven)
BUILT+BAKED — desktop agent in `folder-sync-agent/` (not packaged/shipped yet).
Agent Templates (export/gallery/bind + popup
journey + Studios-page lifecycle UX) BUILT+BAKED.
PWA (installable app + Install button) BUILT+BAKED.
Changelog/"What's new" bell BUILT+BAKED.
Intelligence Layer (8 caps + Studio rail UI) BUILT + BAKED, 5 safe flags
ON by default org-wide. Auto-pilot tab + org-library connector model + 48 Domain Packs + async
auto-train all BUILT + BAKED. STABLE config = `HYBRID_SKILLS=0` / `SUBAGENTS=0`. OPEN BUG: Studio
Queries tab renders blank despite approved `query_library_items` (needs browser console error).
TODO: rebuild image to bake prophet (FORECAST); run train to populate profiler/code-enrich data.
Next ingest work planned in `docs/PLAN_INGEST_STORAGE.md` (Parquet canonical store + LLM merge-judge).
All HTML mockups removed (root `mockup-*`/`ui-mockup*` + `docs/design/*`); `docs/ARCHITECTURE.html` kept.

**Git:** repo on branch `main`, remote `origin` = `git@github.com:raahulgupta07/rahulai-dash.git`
(the older "No git → backups via scripts/backup.sh" note is superseded — git IS live; backups still fine).
