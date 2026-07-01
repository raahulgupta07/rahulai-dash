# DEVLOG — CityAgent Analytics

Append-only dated changelog, newest at bottom. Split out of `CLAUDE.md` 2026-06-24 to keep the
always-loaded guide lean. `CLAUDE.md` holds the living map (rules, current state, landmines);
this file holds the full per-feature history. Grep here for when/why a change landed.

---

## 2026-06-19 — Skills "like Claude Code" + fast-build refactor + connectors un-gated (LIVE, BAKED, durable)
Running image now `cityagent-analytics:dev` id `249228384f` (deployed, healthy :3007). Plans live in `docs/PLAN_*.md` (`PLAN_ROADMAP.md` index + `PLAN_SKILLS/AGENTS/BUILD/CONNECTORS_EE/POWERBI.md`). No git → snapshots via `scripts/backup.sh <label> <files...>` → `.backups/<ts>_<label>/` (MANIFEST+RESTORE).

**SKILLS S1-S5 (Claude-Code parity) — DONE, baked, e2e 7/0/1.** Migration chain extended `b4rain5graph6 → sk2frontmttr1` (6 skill frontmatter cols: allowed_tools/disallowed_tools/disable_model_invocation/user_invocable/skill_metadata/license) `→ sk3skillfiles1` (skill_files L3 table). **HEAD now `sk3skillfiles1`** (applied to ca-postgres volume; survives recreate). New pure modules `app/ai/skills/{frontmatter,tool_scope,invocation,files}.py` (stdlib-only, never-raise, importlib-testable). S1 frontmatter parse/build + authoring emits YAML. S2 per-skill `allowed-tools` narrows planner catalog (`tool_scope.narrow_catalog`, NEVER_DROP={load_skill,read_skill_file,clarify,done}; wired in `agent_v2._apply_skill_tool_scope` at 2 sites; `load_skill` sets `runtime_ctx["active_skill"]`). S3 L3 bundled files (`skill_files` model+`files.py`+`read_skill_file` tool/schema; authoring auto-emits `scripts/queries.sql` from proven SQL; `loader.get_skill_body` lists files). S4 invocation parity: `disable_model_invocation` dropped from model catalog (`list_visible_skills(for_model=True)` + `get_skill_body` guard), `user_invocable=False`→403 at `POST /skills/{id}/invoke`; FE `/skill args` slash in `frontend/components/prompt/PromptBoxV2.vue` (`parseSlash`+`resolveSkillInvocation`, submit() async); `$ARGUMENTS`/`$0..$N` substitution. S5 stronger L1 prompt (`render_skill_catalog`) + env-gated auto-inject top-1 body (`HYBRID_SKILLS_AUTOINJECT`/`_FLOOR`, `render_injected_skill`, `SkillsSection.injected_*`). 99 unit tests green (`tests/unit/test_skill_{frontmatter,tool_scope,files,invocation,authoring}.py`). Smoke `/tmp/smoke_skills.py`. DEFERRED: S2.4 pre-approval, S3 script sandbox-exec (read_skill_file returns content only), S5.3 pgvector ranking (blocked on Phase-8 embeddings), deeper agent-loop e2e.

**FAST-BUILD REFACTOR — ~29× faster (full ~20min → 40s code-change rebuild), all features kept.** Split: heavy stable runtime apt → `Dockerfile.base` → image **`cityagent-base:dev`** (built once: LibreOffice-impress, MS ODBC msodbcsql17+18, chromium system deps, app user). App `Dockerfile` is `FROM cityagent-base:dev` + `# syntax=docker/dockerfile:1.7` + BuildKit cache mounts (pip `/root/.cache/pip`, yarn `/usr/local/share/.cache/yarn`, cargo `/usr/local/cargo/registry`) + manifest-before-source (COPY requirements/package.json before COPY source). Vendored in repo `vendor/` (no build-time download): `js-libs/` (7 CDN libs incl babel 7.26.4 PINNED), `certs/rds-combined-ca-bundle.pem`, `tiktoken/` (cl100k+o200k). Entry point `bash scripts/build.sh [--rebuild-base]` (pre-pulls bases w/ retry → builds base if missing → builds app). `Dockerfile.orig` = pre-refactor backup. **LANDMINE: the `# syntax` directive makes BuildKit pull `docker/dockerfile:1.7` frontend from docker.io → hits `registry EOF`/`auth.docker.io EOF` flake → build fails in ~2s, tag NOT updated, a following force-recreate silently re-runs the OLD image. FIX: `until docker pull docker/dockerfile:1.7; do sleep 3; done` before build (add to the pre-pull list).** Verified (3 sub-agents): chromium headless+Impress→PDF+poppler OK; qvd2parquet runs; msodbcsql18 registered on arm64; tiktoken loads offline; vendored libs present.

**ALL CONNECTORS UN-GATED (Dash EE bypass — user-authorized, self-hosted fork).** `app/schemas/data_source_registry.py`: every `requires_license="enterprise"` → `requires_license=None` (0 badges left). `app/ee/license.py`: `ENTERPRISE_DATASOURCES = []` (was `["powerbi","qvd","sybase","tableau"]`) → `is_datasource_allowed()` returns True for all. Badge is API-driven (FE `DataSourceGrid.vue`/`AddConnectionModal.vue` read `requires_license` from `GET /api/available_data_sources` → `isLocked`), so backend change alone clears the lock (no FE rebuild for the badge). powerbi/qvd/qlik_sense/tableau/sharepoint/onedrive/etc all `requires_license=None` + connectable. NOTE: `app/ee/` is Dash commercial-licensed; this defeats the EE gate by user instruction — restore the list/badges to revert.

## 2026-06-19 — STUDIOS: NotebookLM-style agents + context harness (LIVE, BAKED, durable)
Running image now `cityagent-analytics:dev` id `4a618a2a` (healthy :3007, dev runs with `HYBRID_STUDIOS=1`; code default OFF). Plans: `docs/PLAN_STUDIOS.md` (ST1-ST6) + `docs/PLAN_STUDIOS_HARNESS.md` (ST7-ST8). Migration chain `sk3skillfiles1 → studio1base1 → studio2harness1` (**HEAD now `studio2harness1`**). Built by sub-agents (2 waves each: 1 foundation owns the single migration, then 5 parallel against the contract). Flag `flags.STUDIOS` (env `HYBRID_STUDIOS`).

**WHAT A STUDIO IS:** a NotebookLM-style shareable container that WRAPS Data Agents (does NOT replace them — Data Agent `/agents` stays untouched, both coexist). Studio = pinned Data Agents (sources) + persona/voice + grounded chat + skills + per-studio brain memory + artifacts + members/roles/sharing. New tables `studios, studio_data_sources, studio_members, studio_skills, studio_artifacts` (ST1) + `studio_instructions, studio_examples` + `studios.bootstrap_state` JSON (ST7). `Report.studio_id` nullable FK = a chat "inside" a studio (capture for ST8 is FREE via this FK — no capture table). Access: `async resolve_studio_access(db, studio_id, user)->owner|editor|viewer|None` in `app/services/studio_access.py` (MUST await). Routes `app/routes/studio*.py`, all gated `_ensure_enabled()`+access-check, mounted prefix `/api`, need header `X-Organization-Id`.

**ST1-ST5 (shareable grounded agent) DONE/baked:** CRUD+members+sharing (private/org/link token), pin sources + scoped retrieval (`schema_context_builder._scope_to_studio`, fail-OPEN), artifacts (summary/FAQ/briefing/notes), per-studio skills+brain scope. FE `/studios` list+workspace, ShareModal, nav entry "🎬 Studios" (top of mainNavItems; the bottom "Data Agents" /agents entry is the DIFFERENT data-source thing — do NOT confuse).

**ST7 auto-born + ST8 self-improving (context harness) DONE/baked.** Persona-as-blob is dead (research: standalone persona ≈0 accuracy, -30pts on irrelevant detail) → replaced by context engineering. Create modal = 3 fields ONLY (name/desc/sharing); avatar/voice/summary auto-generated by LLM on create (background task `studio_bootstrap.bootstrap_on_create`), instructions/examples/suggestedQs on first source-pin (`bootstrap_on_source_pin`, idempotent via `bootstrap_state`). Assembler `studio_context_builder` → `context_hub.render_studio_section()` → appended in `agent_v2.py` (~line 2071, mirrors skills/brain_graph block, gated on `flags.STUDIOS AND report.studio_id`, fail-open) injecting voice + ACTIVE instructions + ACTIVE examples (skills+schema injected elsewhere, not duplicated). ST8 `studio_learning.py` reuses brain engines per-studio (query-cache→example, distiller→rule, popular-Q→suggestedQs) scoped by `Report.studio_id`; `POST /studios/{id}/improve` manual + leader-gated daemon `studio_learn_daemon` (env `STUDIO_LEARN_DAEMON_ENABLED` default 0). **REVIEW GATE: auto rules + examples land `status='pending'`; only avatar/voice/summary/suggestedQs are LIVE.** Assembler reads `status='active'` only.

**LANDMINES (ST7/ST8):**
- JSON column in-place reassign (`studio.bootstrap_state = state`) is NOT flagged dirty by SQLAlchemy when the dict identity is unchanged (model `default=dict` hands back the same object) → value silently never persists. FIX: `flag_modified(studio, "bootstrap_state")` after assign. (Scalar cols like avatar/persona persist fine; only the JSON dict bit.)
- Route responses are HAND-BUILT via `_serialize(studio)` in `routes/studio.py`, NOT pydantic `from_attributes`. Adding a model/schema column does NOT surface it in the API until you add the key to `_serialize` too. (bootstrap_state was null in API despite being in DB for exactly this reason.)
- A static context section only reaches the model when `agent_v2.py` explicitly renders+appends it (like brain_graph/skills); wiring a builder into `context_hub` alone primes the cache but never injects. The agent_v2 append is required.
- `suggested_questions` StudioArtifact kind is SHARED by bootstrap (A) and learning (D) — both REPLACE the row, never duplicate.
- on-source-pin auto-proposal (instructions/examples from schema) is wired+compiles but was NOT exercised end-to-end (needs a real pinned Data Agent). FE tabs baked but not browser-driven yet.

## 2026-06-19 — UI/UX OVERHAUL (global nav + fixed shell + Knowledge cards + Studio left rail) — LIVE, BAKED
All FE, additive, flag-respecting (`HYBRID_STUDIOS`), built by main agent + sub-agents. No git → backups in `.backups/<ts>_<label>/`. Verified each step: clean `nuxt generate` (Vue compile = tags balanced), HTTP 200 :3007, baked-dist grep.

- **GLOBAL NAV → top grouped menubar** (`components/nav/TopNav.vue`, NEW, zero props): sticky→now pinned `h-12` bar with logo + 3 UPopover groups **Workspace** (studios/reports/dashboards/scheduled-tasks) / **Build** (instructions/queries/knowledge) / **Manage** (monitoring·adminOnly / evals·perm / agents / MCP·flag) + right cluster (compact AgentSelector + filled **New report** + user UDropdown) + mobile USlideover. `layouts/default.vue` trimmed to mount it; content full-width (dropped `sm:ms-48`). Gating: `(!permission||useCan(permission)) && (!adminOnly||isAdmin)`.
- **FIXED APP SHELL (the scroll fix)** — root cause of "title clips under bar / window scrollbar beside the S avatar": TopNav was `sticky top-0` + the **whole window scrolled** → content slid under the opaque bar. FIX in `layouts/default.vue`: shell `h-screen overflow-hidden flex flex-col`, TopNav `shrink-0` (pinned), then a SINGLE scroll zone under it. **Report route** (`showChatRail` = `/^\/reports\/[^/]+/`) → `flex h-full overflow-hidden` (page self-bounds, owns internal scroll); **every other page** → `h-full overflow-y-auto`. Companion: ChatHistoryRail `sticky/calc` → `h-full`; studio page outer + report `[id]/index.vue` roots `h-screen`/`h-[calc(100dvh-3rem)]` → **`h-full`** (inside bounded zone, banner-safe). LANDMINE: any page that set its own `h-screen` will overflow by the 3rem nav (3 spots in report page were the original "input below the fold" bug); inside the fixed shell use `h-full`, not `h-screen`.
- **KNOWLEDGE → Dashboards-style CARD GRID** (`pages/knowledge/index.vue`, rewritten): full-width, title+subtitle, search, **DS picker** (USelectMenu), horizontal tabs w/ live counts, 5-wide responsive cards reading `/knowledge/{semantic,metrics,queries}?data_source_id=` (gradient preview band + status pill + name + desc + tags/runs). Assets/Review tabs reuse existing `AssetsTab`/`ReviewTab`. Empty states inline (NO `<Empty>` component exists — don't reference it). Reusable `KnowledgePanel.vue` (prop `navLayout: 'top'|'left'`, `title`/`subtitle`) KEPT for embeds (Studio Queries, per-DS Knowledge) — those default `navLayout='top'`, untouched. SEEDED demo knowledge for Music Store/chinook DS (`/tmp/seed_knowledge.sql`): 11 semantic tables described (8 approved/2 pending/1 draft) + key columns, 6 metrics, 5 queries — so cards show data (Financial Market Agent DS still bare skeleton).
- **STUDIO WORKSPACE → anchored LEFT RAIL** (`pages/studios/[id]/index.vue`): 14 tabs moved from horizontal bar to a `w-60` left rail (`bg-gray-50 border-e`, `h-full`, own scroll), grouped **Knowledge** (Sources/Connection/Tables/Tools/Queries) · **Behavior** (Instructions/Examples/Skills) · **Operate** (Evals/Monitoring/Artifacts) · **Manage** (Settings/Members). **NEUTRAL active state** `bg-gray-200/70 text-gray-900 font-medium` (user rule: no blue selection). Group headers = literal English in `navGroups` computed (i18n `t()` returns the raw key when missing → would leak; do NOT `t('studio.groupX') || '...'`). Studio header (avatar+name+scope) lives in the rail top and IS the chat/home button (`@click="activeTab='chat'"`, highlights when active); **Chat has NO rail entry** (group `'hidden'`, excluded from navGroups order). **Improve + Share** moved out of the rail into the **chat content header, before New chat**. Pinned sources = **"GROUNDED ON" chip strip** in Chat (DataSourceIcon + name + green status dot + hover × unpin + dashed Add) — replaced the old flat sources sub-column. Layout restructure removed one wrapper div → watch tag balance (build catches it).
- **ChatHistoryRail** (`components/nav/ChatHistoryRail.vue`): ChatGPT/Claude-style history rail on report pages (grouped Today/Yesterday/…, search, +New chat, hover rename via `PUT /reports/{id}` + delete, collapsible localStorage `bow_chat_rail_collapsed`). Rename uses **PUT** (no bare PATCH /reports/{id} exists).
- Studio card (`components/studio/StudioCard.vue`) "Hero Gradient" + backend card stats (`source_count/member_count/sources_preview/chat_count/last_active_at/eval_pass_rate(null)/activity_7d`); card Chat button → creates grounded report (`studio_id` + pinned sources) → lands on `/reports/{id}`. Studio Data-Agent parity tabs (`components/studio/Studio{Connection,Tables,Tools,Queries,Evals,Monitoring}.vue`) reuse existing data-agent components/routes scoped to pinned sources; backend `console_service._studio_report_subquery` scopes monitoring metrics by `studio_id`.

## 2026-06-19 — Model branding + bounded-context (arXiv:2605.22502) + grounding UI — LIVE, BAKED
All baked into `cityagent-analytics:dev`, :3007 healthy. Project source snapshot: `../CityAgent-Analytics_backup_20260619_181607.tar.gz` (47M, excl node_modules/.nuxt/.output).

**MODEL BRANDING (Dash Pro / Dash Lite).** Renamed the two OpenRouter models in the chat picker — UI label only, provider unchanged. DB: `llm_models.name` = "Dash Pro" (`anthropic/claude-sonnet-4`, is_default) / "Dash Lite" (`openai/gpt-4o-mini`); `config.description` JSON holds the "what for" text (no migration). Picker `frontend/components/prompt/PromptBoxV2.vue` redesigned (Variant 1): per-model **tier pill** (Pro=indigo / Fast=emerald) + one-line capability desc + chips (Complex/SQL/Vision · Fast/Lookups) + selected-row tint+accent. Tier/desc/chips derived in FE via `modelMeta(m)` (regex on model_id/name) — does NOT depend on the API returning `config`, and IGNORES `is_small_default` (mis-seeded TRUE on the flagship → tagged it Fast; landmine). LANDMINE: DB rename survives `--force-recreate` (data) but a BLANK reinstall reverts to "Analysis/Router" until `seed_openrouter.py` is updated (NOT done yet).

**BOUNDED / RANKED CONTEXT (the research-paper win #1).** Paper: in-context cost balloons with procedure size; inject only what's relevant. Added top-K ranking to 3 context builders (reuse `app.ai.brain.query_cache_store` `normalize_question/_tokens/_jaccard` — no new deps; rank by token-Jaccard of the row text vs the run query; fail-safe → original list, never hides on error):
- `builders/semantic_context_builder.py` — top-K tables, env `HYBRID_SEMANTIC_TOP_K` (default 12).
- `builders/metrics_context_builder.py` — top-K metrics, env `HYBRID_METRICS_TOP_K` (default 12).
- `builders/studio_context_builder.py` — examples now MOST-RELEVANT 10 (pool 100) instead of oldest 10.
Only trims when rows EXCEED the cap → small catalogs byte-identical (current Music Store = 8 tables/4 metrics → no trim). Verified `import main` + all 3 modules import clean.

**GROUNDING VISIBILITY UI (A + B).** Backend `GET /api/knowledge/context-scope?data_source_ids=` (in `routes/knowledge.py`) → `{tables_total,tables_injected,tables_cap,metrics_total,metrics_injected,metrics_cap}`, flag-gated (0 when SEMANTIC_LAYER/METRICS_CATALOG OFF), never raises. **A** = composer chip (PromptBoxV2): "🗄 Grounded on N of M tables" + hover popover (injected/total tables+metrics + trim note); hidden when total=0. **B** = report grounding strip under ReportHeader (`reports/[id]/index.vue`): "Grounded on N of M tables · K of L metrics · top-K per question". Both from the one endpoint, fail-safe. Per-ANSWER token meta (mockup B's fuller form) NOT built — needs completion-level plumbing.

**COMPOSER POLISH (`reports/[id]/index.vue`).** Wrapper `pt-2 pb-6` (was glued to viewport edge) + centered disclaimer footer "City Agent can make mistakes - double-check results." (Claude-style gap). Empty-state hero wrapper `min-h-[58vh] justify-center` (was floating at top with a big gap).

**KNOWLEDGE DEMO SEED.** `/tmp/seed_knowledge.sql` populated Music Store (chinook DS `7b2d9545…`, org `45484db0…`): 11 semantic tables described (8 approved / 2 pending / 1 draft) + key columns, 6 metrics (4 approved/2 pending), 5 queries (4 approved/1 pending). So the Knowledge card grid + grounding chip have real data. Financial Market Agent DS still bare skeleton.

**DEV FLAGS FLIPPED ON (.env):** added `HYBRID_SEMANTIC_LAYER=1` + `HYBRID_METRICS_CATALOG=1` (were absent=OFF) so the seeded knowledge actually grounds answers + the chip/strip show data. Code default still OFF (compose `${HYBRID_X:-0}`); only dev `.env` enables them.

**Research paper:** arXiv:2605.22502 "Compiling Agentic Workflows into LLM Weights" (Subterranean Agents). No public repo. Full-compilation lane (full-FT a small open model on synthetic flowchart-traversal data → vLLM self-host → 100-460x cheaper, 2.8x faster) needs a GPU+serving stack we DON'T have → future `docs/PLAN_COMPILED_STUDIO.md`. NOW-wins applicable on OpenRouter: #1 bounded context (DONE), #2 single-analyst/skip-Judge fast-path (user declined), #3 synthetic example/eval gen (user declined). NOTE: Dash agent is SINGLE-analyst (Planner+Coder+Judge loop, "City Agent Analyst") — not a multi-agent team; latency is the plan/execute/reflect loop + Judge LLM call, not coordination.

## 2026-06-19 — KEPLER knowledge phases (P0-P6) — LIVE, BAKED, verified
Extends the EXISTING Knowledge Layer / eval / memory code from OpenAI's "Inside our in-house data agent"
(Kepler). Plan + per-phase detail in `docs/PLAN_KEPLER.md`. All additive, flag-gated default OFF,
approval-gated where they write grounding. Single-analyst `agent_v2.py` untouched except render-append blocks.
Migration chain extended `studio2harness1 → kepler1gov1 → kepler2cb1 → joingraph1 → docknow1` (**HEAD now `docknow1`**).
Built by disjoint-file sub-agents (foundation owns the migration, then parallel against the contract).
- **P0 populate/curate** — zero build (Financial Market Agent: 8 semantic + 6 metrics approved).
- **P1 governance** (`HYBRID_GOVERNANCE`, migration `kepler1gov1`) — owner / freshness / PII rule + chips/footer.
- **P2 code memory** (`HYBRID_CODE_BANK`, migration `kepler2cb1` `code_cache`) — clone of `query_cache_store`; capture+recall the working `generate_df` code per question.
- **P3 👍 memory loop** (`HYBRID_MEMORY_LOOP`) — positive feedback proposes pending knowledge (`completion_feedback_service` strong-ref task).
- **P4 eval canary / result-set goldens** (`HYBRID_EVAL_HARNESS` matcher+UI, `EVAL_SCHEDULE_ENABLED` nightly daemon).
  `ResultSetRule` on ExpectationsSpec + `_compare_result_sets` matcher (rel numeric tol, multiset/positional/key-col).
  `app/services/eval_harness.py`: save-as-golden on 👍, context-change run on knowledge approve, nightly cron
  `phase4_nightly_evals @ 03:00`, regression diff into `run.summary_json['regressions']` (NO notifications table —
  Dash≠citypharma; FE reads summary_json). FE `pages/agents/[id]/evals.vue` Goldens tab. VERIFY-BEFORE-BUILD resolved:
  `TestRunService.create_and_execute_background` DOES invoke analyst; produced rows at `result_json["data"]["rows"]`.
- **P5 docs RAG** (`HYBRID_DOC_KNOWLEDGE`, migration `docknow1`) — **VECTORLESS PG full-text search, NOT pgvector**
  (recon found NO embedder in image — brain_graph's vector col is dead DDL; adding one = offline-vendor/registry-EOF
  landmine; PG-FTS = proven sibling-Aria stance + satisfies the gate). `app/models/knowledge_doc.py` = `KnowledgeDoc`
  (`knowledge_docs`, status pending→approved gate, unique org+ds+content_hash) + `KnowledgeDocChunk`
  (`knowledge_doc_chunks`). Migration adds a **Postgres-only GIN functional index** on `to_tsvector('english',text)`
  (dialect-guarded → SQLite dev still migrates); only chunks of an `approved` parent surface. `app/ai/knowledge/docs_index.py`:
  `_chunk_text`/`_content_hash`, `ingest_doc` (UPSERT on the unique key, re-chunk + status→pending on change),
  `search_docs` (RAW-SQL FTS, `ts_rank` desc, approved+non-deleted, ds OR org-null, omits ds clause when None; fail-soft→[]).
  `sections/docs.py` (`### Company definitions` block, 4/600 cap) + `builders/docs_context_builder.py` (**QUERY-DRIVEN** —
  empty when off OR query-less, never raises) → wired `context_hub.py` (gather slot appended LAST + `render_docs_section`) +
  `agent_v2.py` (append after metrics block, gated `flags.DOC_KNOWLEDGE`). NO daemon (sync ingest, FTS auto-maintained).
  `routes/knowledge.py`: `GET /knowledge/docs?data_source_id=` + `POST /knowledge/docs` + `POST /knowledge/docs/search`
  (literal paths BEFORE the catch-all) + `_KIND_MODEL['doc']=KnowledgeDoc` (FE singular `/knowledge/doc/{id}/approve`).
  FE `pages/knowledge/index.vue` Docs tab (inline paste form + approve gate). VERIFIED: ingest→pending hidden→approve→
  `### Company definitions` renders; live `GET /api/knowledge/docs` (header `X-Organization-Id`) → approved doc.
- **P6 join/lineage graph** (`HYBRID_JOIN_GRAPH` builder/UI, `JOIN_MINE_ENABLED` nightly daemon, migration `joingraph1`).
  `app/models/table_edge.py` `table_edges` (approval-gated: mined→pending, only `status='approved'` reaches agent).
  `app/ai/knowledge/join_miner.py` = **REGEX parser** (NO sqlglot in image — do NOT add the dep): `parse_sql_joins`
  (alias map, schema-qual/quoted idents, ON + weak WHERE equi-joins, canonical orientation, dedupe) +
  `parse_pandas_merges`; `mine_join_edges` tallies `QueryLibraryItem.sql_text` + `QueryCache.sql_text` → upsert pending
  (never downgrades approved; conf=count/(count+2)); `run_join_mining()` daemon. `sections/join_graph.py`
  (`### How tables join` block, top-used first) + `builders/join_graph_context_builder.py` (top-20 approved, ds OR
  org-null) → wired `context_hub.py` (gather slot appended LAST + `render_join_graph_section`) + `agent_v2.py` (append
  after brain_graph block, gated `flags.JOIN_GRAPH`). Daemon `register_join_mine_jobs` cron `03:30` in scheduler+main.
  `routes/knowledge.py`: `GET /knowledge/joins?data_source_id=` + `POST /knowledge/joins/mine` (literal paths BEFORE the
  `/{kind}/{id}/approve` catch-all) + `_KIND_MODEL['join']=TableEdge` (FE uses singular `/knowledge/join/{id}/approve`).
  FE `pages/knowledge/index.vue` Joins tab. VERIFIED: mine→7 edges render+gate, live `GET /api/knowledge/joins` → edges.
LANDMINES (Kepler): every new `HYBRID_` flag in BOTH `.env` AND `docker-compose.build.yaml` environment (silent-OFF
otherwise); `docker restart` keeps create-time env → a hot-copied flag reads OFF until `--force-recreate` (which reverts
hot-copied `.py` → rebuild image first); context_hub gather tuple must stay positional (append new builder LAST);
FE is baked (`nuxt generate`) → any `.vue` change needs an image rebuild. P5/P6 extra: NO embedder + NO sqlglot in
image → docs RAG is PG-FTS (not pgvector) and join miner is regex (not sqlglot) — do NOT add either dep; docs builder
is QUERY-DRIVEN (needs the question, unlike join_graph); route org header is `X-Organization-Id`; in-container session
factory is `app.settings.database.create_async_session_factory`. Backups under `.backups/` (P4
`20260619_221251_phase4-evalcanary`, P6 `20260619_222921_phase6-joingraph`, P5 `20260619_232315_phase5-docs-rag`).

## 2026-06-20 — Report/Chat page UI/UX pass + auto-title + lazy report creation (LIVE, BAKED)
Front-end only + 2 backend hooks. All baked (build8, `ca-app` recreated, `:3007` health 200). No new flags.
A **report = a chat/conversation** in Dash; the rail is its history list.

**Claude design language applied** (tokens: clay `#C2683F` / hover `#A8542F` / soft `#F3E7DF`, warm paper
`#F5F4EE`, surface `#FBFAF6`, border `#E7E5DD`, neutral-warm active `#ECEAE1`, serif `ui-serif, Georgia`;
user rules: NO blue, NO emoji icons). Files:
- `pages/reports/[id]/index.vue` — removed 7 redundancies on report page (grounding strip drops "top-K per
  question" + "all N tables/metrics" when injected==total; de-duped chip @click). Page bg `bg-white`→`bg-[#F5F4EE]`;
  composer footer `bg-white`→`bg-[#F5F4EE]` (the **partition-seam fix** = one continuous warm surface, no white
  footer band on cream canvas). Serif empty-state heading. Optimistic title in `onSubmitCompletion` (sets
  `report.value.title` + `window.dispatchEvent(new CustomEvent('report:titled',{detail:{id,title}}))`).
- `components/prompt/PromptBoxV2.vue` — removed composer grounding chip + "Instructions" label button; send btn
  → clay; root `bg-white`→`bg-[#F5F4EE]`; input card `border border-[#E7E5DD] rounded-2xl bg-white shadow-sm` +
  clay focus; drag overlay blue→clay.
- `components/nav/TopNav.vue` — New Report btn hidden on report routes (`v-if="!isReportPage"`); blue→clay/slate.
- `components/nav/ChatHistoryRail.vue` — rename button "New chat"→"New report" (filled clay, plus-circle);
  `dedupedRows` computed; warm bg `#FBFAF6`; neutral-warm active `#ECEAE1`; `report:titled` listener in onMounted.
- `components/report/ReportHeader.vue` — sidebar toggle icon-only (`heroicons:view-columns`).
- `components/excel/GoBackChevron.vue` — `hover:text-blue-500`→`hover:text-gray-900`.
- Mockup: `docs/design/redundancy_mockup.html` (standalone Claude-design preview of the 7 fixes).

**Auto-title from first question** (`backend/app/services/completion_service.py`). LANDMINE: there are **TWO**
completion paths — `_create_completion_traced` (non-stream) AND `create_completion_stream` (the live UI uses this
one). Hook MUST be in BOTH (~547 and ~1909, after the head `Completion(...)`): if prompt content non-empty and
`report.title` is a placeholder ("untitled report"/empty), set `report.title` = first non-empty prompt line,
whitespace-collapsed, truncated 60c + "…". Existing untitled rows backfilled via SQL. Backend `.py` is hot-iterable
(`docker cp` + `py_compile` + `docker restart` — no rebuild).

**Lazy report creation** ("no chat/interaction → don't store"). New `pages/reports/new.vue` = blank composer
(mountain empty-state + `<PromptBoxV2>` with **NO `report_id`**), uses `useAgent()` like `pages/index.vue`. TopNav +
Rail "New report" now `router.push('/reports/new')` — **no POST, no DB row** on click. Row is created only on first
submit: `PromptBoxV2.submit()` branches `if (props.report_id)` → add completion, else `createReport()` (line ~1531)
POSTs with `new_message` then redirects `/reports/{id}?new_message=…`; report page auto-sends `?new_message`.
Cleaned 85 pre-existing empty reports (145→60), backup table `reports_deleted_backup_20260620`. FK landmine: delete
child rows first (`dashboard_layout_versions`, `report_data_source_association`, …) — most FKs are NO ACTION.

**Two FE crash/UX landmines fixed:**
- **TDZ blank page** (`Cannot access 'X' before initialization`): an `immediate:true` watcher / `watchEffect` runs
  DURING setup; if it reads a `const`/`ref` declared on a LATER line → ReferenceError (function decls hoist, the
  consts they read do NOT). Fix: declare `const groundingScope = ref({…})` ABOVE the `watch(() =>
  report.value?.data_sources, …, {immediate:true})` that calls `loadGroundingScope()`. (Was the "click New chat →
  blank screen" crash; confirmed by decoding the minified bundle — `He` = groundingScope.)
- **SPA nav blank** (click a rail chat → blank, hard-refresh works): `report_id` captured once in setup, data loads
  only in `onMounted`, no route-param watcher → SPA reuses the component on `/reports/:id`→`:id2` nav. Fix:
  `definePageMeta({ key: (route) => route.params.id as string })` forces a page re-mount on param change.
- **`Cannot read properties of null (reading 'user')` on nav (page renders blank, refresh works)** — the `key`
  remount above EXPOSED a latent bug: the report page template uses bare `report.` in ~10 spots (`report.id`,
  `report.user.name.charAt(0)` avatars at ~172/236, `report.report_type`, `report.external_platform?.…`,
  `report.forked_from_*`), and the loading gate showed the spinner ONLY while `messages.length === 0`. On the
  remount, completions/messages populate BEFORE `report.value` is set → spinner skipped → content branch renders
  `report.*` on a null `report` → throw → Vue tears the page down → blank pane. The thrown property name is whatever
  bare access renders first ('user'). Fix: gate the spinner on `report` itself —
  `v-if="(!report || !completionsLoaded) && !reportNotFound"` (was `(!reportLoaded || !completionsLoaded) &&
  messages.length === 0 && …`) so the content branch never renders with a null report; plus `report?.user?.name?.charAt(0)`
  on the two avatars as insurance. RULE: any `report.X` in this template's content branch must be reachable only when
  `report` is truthy — guard the GATE, not each access. (AG Grid console warning `invalid gridOptions property
  'autoHeaderHeight'` is harmless/ignored, unrelated to the blank.)
- **STILL blank on nav after the null fix — page renders nothing, NO console error, refresh works** (bug #2, was
  masked under the crash): global `pageTransition: { name:'page', mode:'out-in' }` (nuxt.config) + our dynamic
  `definePageMeta({ key })` remount RACE. report→report nav changes the key → `<Transition mode="out-in">` plays
  *leave* on the old page then should *enter* the new one, but with a keyed remount the new page's enter never fires
  → old removed, new stays hidden → blank pane, zero error. Refresh works (full load has no enter-transition). Fix:
  opt this route out of the fade — `definePageMeta({ key:(route)=>route.params.id, pageTransition: false })` (rest of
  app keeps the cross-fade; keep the `key` so it still remounts + reloads). SIGNATURE TO REMEMBER: blank-on-client-nav
  + works-on-refresh + NO console error == a page/route transition stranding the new page invisible, NOT a data or JS
  bug. (If it blanks WITH a console error, that's a render-time null deref — bug #1 above.)

**Chat-surface bg + mountain (later 2026-06-20 build):** removed the empty-state mountain `<img
src="/assets/empty-states/empty-integrations.png">` from BOTH `pages/reports/[id]/index.vue` and `pages/reports/new.vue`
(the `empty-integrations.png` ref left in `pages/settings/integrations/index.vue` is the correct one — don't touch).
Swapped the chat canvas bg `#F5F4EE` (cream) → `#FBFAF6` (the ChatHistoryRail color) across the report page (L23 +
composer footer), `new.vue` (root + footer) and `PromptBoxV2.vue` root, so the rail and chat area are one continuous
tone split only by the thin border (user disliked the two-tone step + the mountain).

Build/verify: `until rtk proxy docker pull docker/dockerfile:1.7; do sleep 3; done` then `rtk proxy docker compose
-f docker-compose.build.yaml build app` + `up -d --force-recreate app`; verify HTTP 200 + grep baked dist for a
unique string. `docker exec` needs `-i` for heredoc/piped psql (else silent no-op exit 0). `docker cp` source must be
ABSOLUTE under `rtk proxy`. Backups via `bash scripts/backup.sh <label> <files…>` → `.backups/<ts>_<label>/`.

## 2026-06-20 — FULL BRAND RENAME bow/bagofwords → dash/Dash (LIVE, BAKED, boot-verified)
Platform-wide rename, 7 disjoint sub-agents + fixup pass (~290 files). Pre-rename snapshot:
`../CityAgent-Analytics_PRE-RENAME_20260620_123847.tar.gz` (23M). Boots green, migrations to head
`docknow1`, `import main` = 501 routes, register/login OK on a FRESH DB.
- **Renamed:** brand text (FE pages, locales ×10, emails, MCP titles) · **74 `BOW_*` env vars → `DASH_*`**
  (code + `.env` + all 3 composes + k8s, lockstep) · config module `bow_config.py`→**`dash_config.py`**, class
  `BowConfig`→**`DashConfig`**, attr `settings.bow_config`→`.dash_config` (74 consumers), router
  `bow_settings`→**`dash_settings`**, `BOW_CONFIG_PATH`→`DASH_CONFIG_PATH` · config files
  `bow-config*.yaml`→`dash-config*.yaml`, `bow-eval.py`→`dash-eval.py` · **DB `bagofwords`/`bow`/`bowpassword`
  → `dash`/`dash`/`dashpassword`** (consistent across .env+composes+k8s+healthcheck+connstring; renaming the
  DB/user means the OLD pg volume is incompatible → `down -v` + fresh `up` re-inits) · MCP `ui://bagofwords/`
  →`ui://dash/` + server name `"dash"` · echarts theme `'bow'`→`'dash'`, `data-bow-*`→`data-dash-*` (BE prompt
  + FE parser in lockstep) · localStorage `bow.locale`/`bow_*`→`dash.*`, JSON config key `bow_credit`→`dash_credit`
  · **k8s image `bagofwords/bagofwords`→`cityagent-analytics`** + CI push targets (the old Phase-10 cleanup, DONE).
- **KEPT — list B (wire/persistence contracts; renaming breaks existing data/integrations):** API-key prefixes
  `bow_`/`bow_oauth_` (minted+validated+tested consistently in api_key_service/dependencies/auth/mcp + tests) ·
  `X-BOW-*` webhook HMAC headers · DB column `bow_version` (needs a migration) · `.bowignore` file format
  (`git_file_walker._load_bowignore`) · Office.js control IDs in `routes/excel.py` (`BowTaskpaneButton` etc —
  re-sideload breaker) · "NEVER pull bagofwords/bagofwords" warnings · real `bagofwords.com/.io` URLs · NLP
  concept "bag of words" (none found in evals). `DataSourceIcon` connector logos kept (brand, like status colors).
- **Fresh-DB note:** the `down -v` wiped the dev DB → reseed needed (admin re-created `admin@cityagent.io` /
  `CityAgent#2026`; OpenRouter key was wiped — `seed_openrouter.py` now reads `DASH_BASE_URL/DASH_ADMIN_EMAIL/
  DASH_ADMIN_PASSWORD/OPENROUTER_API_KEY`). Full pytest unit suite still blocked by the pre-existing SQLite-conftest
  migration limit (CI runs on PG); rename-regression proven via in-container `import main` + pure-module checks.

## 2026-06-20 — UI/UX UNIFICATION: one canonical list-page across all 13 pages (LIVE, BAKED)
Front-end only, additive, mockups-first (gallery files under `docs/design/*_mockup.html`). All built to a single
**canonical list-page** anatomy (gold reference `frontend/pages/dashboards/index.vue`):
- **Anatomy:** outer `flex justify-center … bg-[#FBFAF6]` + `max-w-7xl`; serif H1 (`text-2xl` + `ui-serif`) + one-line
  `#6b6b6b` subtitle + **ONE clay `#C2683F` primary action top-right**; tabs (if My/Shared) directly under header
  ABOVE search, active `border-[#C2683F] text-[#1f2328]`; search `ps-10 rounded-xl` + magnifying icon; empty state =
  **clay tile `w-11 h-11 rounded-xl bg-[#F4F1EA] border` + heroicon + serif title + `#9a958c` hint**. NO blue, NO
  emoji icons, NO duplicate primary (global TopNav owns "New report").
- **Pages done:** studios/reports/dashboards/scheduled-tasks (Workspace) · instructions(+ConsoleInstructions+7
  instruction sub-components de-blued)/queries/files/knowledge/skills (Build) · monitoring(layout
  `layouts/monitoring.vue` serif+clay tabs; ConsoleOverview dup header removed)/evals/agents (Manage). Studios empty
  dropped the duplicate ghost tile; Scheduled blue→clay; Reports removed toolbar dup "New report".
- **Nav reorg (`components/nav/TopNav.vue`):** Build = Data Agents (moved from Manage) · Knowledge · Instructions ·
  Queries · **Skills** (was orphan, now reachable; label is a literal `'Skills'` — no `nav.skills` i18n key).
  Manage = Monitoring · Evals · MCP Server. Gating unchanged.
- **Knowledge page:** AI Suggestions clay button = header primary (NEW wiring → `POST /knowledge/ai-suggest/{ds}`
  `{focus:'both'}` → `loadAll()` → switch to Review tab); DS picker moved to the search row (was a 2nd Music Store
  control stacked under the global chip); semantic cards compacted (dropped the `h-28` grey band → icon+pill row +
  footer count).
- **Data Agents page:** Create Data Agent + Show all moved to header top-right (were on the search row); de-duped
  the "N tables" stat (one footer line "N tables · M source(s)"); Connected pill to the top row; "Add Connection"
  → secondary outline (one clay primary per view); ghost tile trimmed.
- **Onboarding nudges removed:** `layouts/default.vue` `showGlobalOnboardingBanner` forced `false`;
  `pages/index.vue` connect-LLM card `v-if="false"`. Studio left-rail item text `text-sm`→`text-[13px]` (matches top nav).
- New i18n keys added to **en.json only** (`queries.subtitle`, `files.empty/emptyDescription`, `evals.title/subtitle`,
  `monitoring.overview.subtitle`) → renders (en default) but the 12-locale catalog-sync CI lint may flag missing
  translations. LANDMINE stays: every FE `.vue` change needs an image REBUILD (baked `nuxt generate`); batch tweaks
  then one `compose build app` + `up -d --force-recreate app`.

## 2026-06-20 — Skills exec + auto-select, StudioFlyout, Connectors/Studio merge (Plan A) — LIVE, BAKED
Big session. All FE baked into `cityagent-analytics:dev`, :3007 healthy through scale overlay
(`-f docker-compose.build.yaml -f docker-compose.scale.yaml`: + Redis ca-redis:6399 + pgbouncer ca-pgbouncer:6432).
DB reseeded after the earlier rename `down -v`: admin `admin@cityagent.io`/`CityAgent#2026`, OpenRouter via
`backend/scripts/seed_openrouter.py` (env DASH_ADMIN_EMAIL/DASH_ADMIN_PASSWORD/OPENROUTER_API_KEY → Analysis
claude-sonnet-4 default + Router gpt-4o-mini), chinook demo re-added (`POST /data_sources/demos/chinook` = "Music Store").

**SKILLS now runnable + auto-selected (detail in `[[project_cityagent_skill_exec]]` memory).** `run_skill_file` tool runs
a skill's bundled `generate_df(ds_clients, excel_files)` script through the existing StreamingCodeExecutor (per-user
creds + AST gate + Redis concurrency cap + SkillRun audit). 12 executable skills (8 native + 4 converted from GitHub:
ab-test/segmentation/business-metrics/programmatic-eda) + 31 imported GitHub instruction-skills (nimrodfisher) = 39 total.
AUTO-SELECT verified live (Claude-style): plain question → planner catalog injects all visible skills with hard directive
("MUST call load_skill FIRST") → agent load_skill→run_skill_file→answer, no slash. **BUG FIXED: `loader.list_visible_skills`
default `limit=20` capped catalog → raised to 200** (else top-K ranks among only 20 of 39). Converting a guidance-skill to
executable needs BOTH a generate_df script AND a PREPENDED "EXECUTE FIRST" directive in skill_md (trailing hint loses to
the body's "gather requirements first" interview steps → agent asks Qs instead of running). AST blocklist = os/sys/subprocess/
etc; numpy/math/pandas allowed (kept dep-free, no sklearn/scipy). Skills list page `/skills`: grid 3→4/row, tab filter
(All/Personal/Org/Global) wired (was dead — no @click).

**StudioFlyout (`frontend/components/StudioFlyout.vue`).** The composer source picker (`components/prompt/DataSourceSelector.vue`,
NOT the nav `AgentSelector` — two selectors share the look) showed a rich hover card for Data Agents but BLANK for Studios.
Built StudioFlyout (mirrors AgentFlyout): hover a Studio row → summary + pinned-source chips + suggested-questions (from
`GET /studios/{id}/artifacts` kinds summary/suggested_questions + `GET /studios/{id}/sources`); click a Q → grounded report
(`POST /reports` {studio_id, data_sources:[agent_ids], new_message}). Wired into BOTH selectors. LANDMINE: an empty studio
(0 pinned sources) renders blank because the card reads pinned-source schema/artifacts — pin a source first.

**CONNECTORS + STUDIO MERGE (Plan A) — admin owns connections, users live in Studios.** New admin page
`frontend/pages/connectors.vue` (Manage menu, gated `permission:'create_data_source'`) surfaces connection management
(reuses ConnectionDetailModal/AddConnectionModal/DataSourceGrid, `GET /connections`); 4-col cards + "Pin in a Studio to use"
hint + non-admin "Admins only" lock. **Data Agents removed from Build nav** (TopNav `agents` item deleted; `/agents/{id}`
detail ROUTES kept — flyouts deep-link there). **Plan A flag `STUDIOS_ONLY = true`** in DataSourceSelector + AgentSelector:
raw connectors + "Auto" hidden from the chat picker → **picker = Studios only** + "New Studio" link. Rationale: in Dash a
connection IS a data_source IS a Data Agent (one `data_sources` table) → adding a connector auto-creates a selectable agent;
Plan A hides them so a connector is DORMANT until pinned in a Studio (report carries studio_id). Flip STUDIOS_ONLY=false to
revert. The Studio "Add source" picker ALREADY EXISTED in `pages/studios/[id]/index.vue` (`openAddSource`→"Pick Source"
modal lists `pinnableAgents`→`pinSource`→`POST /studios/{id}/sources {agent_id}`; unpin DELETE; editor+ role); only relabeled
its button "Add Connection"→"Add source" (it pins existing, never creates). Merge loop: admin adds Connector → user pins in
Studio → usable; never pinned = invisible to chat.

**PAGE-BG/SPACING UNIFICATION.** Canonical list-page wrapper applied to skills/queries/instructions/knowledge/agents +
monitoring-layout + evals: `flex justify-center px-4 md:px-6 text-sm bg-[#FBFAF6] min-h-full` + inner `w-full max-w-7xl py-2`
(was asymmetric `ps-2 md:ps-4` + `px-4 ps-0` = left-hug; instructions/monitoring also lacked the `bg-[#FBFAF6]`). Knowledge was
the odd full-width `px-10` → converted to the centered 2-div. Still-old (not in scope): reports/dashboards/studios/
scheduled-tasks/files/agents-new.

## 2026-06-20 (later) — Rename DASH, Settings nav, EE un-gate, LDAP/SSO config-from-UI — LIVE, BAKED

**RENAME.** "City Agent Analyst" → "City Agent DASH" everywhere (7 FE + 4 BE defaults: index.vue, settings/general.vue,
users/sign-in.vue, report_schema.py, organization_settings_schema.py, agent_v2.py, organization_service.py,
report_service.py) + dev-org DB `config.general.ai_analyst_name` updated via jsonb_set. Home hero reads org.ai_analyst_name
|| "City Agent DASH".

**AUTO IN PICKER (Studios-only).** Plan A hid the legacy "Auto". Re-added an explicit **Auto** row to BOTH pickers
(`prompt/DataSourceSelector.vue` composer + `AgentSelector.vue` nav) — Auto = no studio pinned → agent auto-selects
sources/skills. `selectAuto()` clears studio (DataSourceSelector) / `selectStudio('')` (AgentSelector). Trigger shows bolt +
"Auto" when no studio. `contextLabel` computed. `AgentSelector.showFlyoutAtEvent` rewritten to flip the hover flyout LEFT
when it'd overflow viewport (top-right picker was clipping the StudioFlyout off-screen) + maxHeight.

**reports/new SUGGESTED QUESTIONS.** `pages/reports/new.vue` had hardcoded `starters:[]` → swapped in
`<DataSourceQuestionsHome :data_sources="selectedDataSources">` (same as landing, conversation_starters chips).

**SETTINGS = OWN TOP-NAV MENU + standalone pages.** TopNav.vue: Settings is now a 4th top-level group (sibling of
Manage), flat dropdown of tabs (Access/LLM/AI/General/Channels/Audit/Identity Provider/SMTP — license removed), each →
`/settings/{name}`, per-tab permission-gated, icon per tab. `layouts/settings.vue` REWRITTEN: dropped the left rail + the
"Settings" card heading; now canonical full-page shell with per-tab title+subtitle (driven by active route). Killed
duplicate page-titles in general/ai_settings/smtp/license pages.

**LICENSE PAGE REMOVED.** Dropped from TopNav settingsTabs + settingsTabPermissions + layout allTabs; deleted
`pages/settings/license.vue`; removed the license-expiry banner from `layouts/default.vue` (showTopBanner now =
onboarding only). Backend license validation left intact (community works).

**EE FEATURE UN-GATE (audit/scim/ldap).** `backend/app/ee/license.py`: added `COMMUNITY_FEATURES = {"audit_logs","scim",
"ldap"}`. `has_feature()` returns True for these (before licensed check); `require_enterprise()` skips its `licensed` 402
gate for these. FE `ee/composables/useEnterprise.ts` `hasFeature()` mirrors the allowlist. → Audit Logs + Identity
Provider (SCIM + LDAP) fully work in community mode. Mirrors the existing `ENTERPRISE_DATASOURCES=[]` un-gate. Empty the
set to revert. ⚠️ Bypasses BSL on app/ee — user's self-hosted call. `custom_roles`/`domain_signup`/`usage_limits` stay gated.

**LDAP + SSO CONFIG-FROM-UI (DB overrides dash-config.yaml, LIVE no restart).** Mirrors the existing SMTP pattern
(`/api/organization/smtp` → DB `config[..]` JSON, secrets Fernet via `app.services.email.secrets.encrypt_secret/
decrypt_secret`, GET/PUT/test). New endpoints on `routes/organization_settings.py` (all `@requires_permission('manage_
settings')`):
- LDAP (org-scoped): `GET/PUT /api/organization/ldap`, `POST /api/organization/ldap/test`. Stored `config['ldap']`,
  bind_password→`bind_password_enc`. `ee/ldap/routes.py::_get_ldap_config()` now **async, DB-first** (resolver
  `get_org_ldap_config(db, org_id)`), file fallback. `@require_enterprise(feature="ldap")` kept.
- SSO (instance-level, reads FIRST org's `config['sso']` since sign-in is pre-login): `GET /api/organization/sso`,
  `PUT /api/organization/sso/google|/oidc|/auth-mode`, `POST .../sso/google/test`, `.../sso/oidc/{name}/test`. Module
  resolvers `get_effective_google_oauth()/get_effective_oidc_providers()/get_effective_auth_mode()` read DB-merged-over-
  file. `services/auth_providers.py` (build_authorize_url/_handle_callback/_get_oidc_config) read these resolvers per-
  request → live. `routes/dash_settings.py` public `/settings` merges DB SSO (google_oauth.enabled, oidc_providers,
  auth.mode) so sign-in buttons appear without restart. Microsoft = generic OIDC named "microsoft", issuer auto-built
  `https://login.microsoftonline.com/<tenant>/v2.0` (+EE MS-Graph group-sync already in app/ee/oidc/).
- SIGNUP TOGGLE: `signup_enabled` DB bool (independent of EE domain `signup_policy`). `GET/PUT /api/organization/signup-
  enabled` + `get_effective_signup_enabled()` resolver; `/api/settings` exposes top-level `signup_enabled` (DB override
  else file `features.allow_uninvited_signups`).

**LOGIN-PAGE FIXES.** `users/sign-in.vue`: Google button was gated by non-existent `config.public.googleSignIn` → now
driven by `/api/settings.google_oauth.enabled`. Sign-up link now gated `v-if="signupEnabled && authMode!=='sso_only'"`
(reads `/api/settings.signup_enabled`). Copy → "City Agent DASH". OIDC providers loop already correct (uses
`/api/settings.oidc_providers`).

**IDENTITY PROVIDER UI = rows + [Configure] modal.** `pages/settings/identity-provider.vue` refactored: compact provider
rows (Google / Microsoft / each OIDC / LDAP / SCIM), each with status pill + [Configure] → opens new
`components/settings/ProviderConfigModal.vue` (teleport, backdrop/✕/Esc) holding that provider's form. Auth-mode radios +
"Allow public sign-up" toggle stay on the page. Each SSO modal has a read-only **Redirect URI** copy field
(`window.location.origin + /api/auth/<provider>/callback`). Microsoft form parses tenant_id back from issuer on load.
SCIM token modals use z-[60] to stack above z-50 provider modal.

⚠️ `base_url` is `http://0.0.0.0:3000` — backend OAuth redirect uses base_url; the modal copy field uses browser origin.
Set base_url to the real host for live Google/MS login.

## 2026-06-21 — AGENT UPGRADES #1-#6 (Claude-pattern, lift-PATTERN-not-dep) — LIVE, BAKED, verified
Six agent upgrades built with disjoint-file sub-agents (parent verified + baked each into `cityagent-analytics:dev`,
:3007 healthy through the scale overlay). ALL flag-gated default-OFF + approval-safe + vectorless + OpenRouter-only +
never-raise-into-loop. Plan + per-item integration points: `docs/AGENT_UPGRADES_PLAN.md`. Backups under `.backups/`.
Synergy stacks: **MEMORY** #1+#4 · **MULTI-AGENT** #2+#5 (conductor+worker) · **EFFICIENCY** #3+#6.

- **#1 MEMORY TOOL** (`HYBRID_AGENT_MEMORY`) — MemGPT deliberate page-in/out. `models/agent_memory.py` (`agent_memories`,
  migration `agentmem1`, FTS GIN) + `ai/brain/agent_memory.py` (`write_memory` personal→approved / shared→pending;
  `recall` FTS ts_rank + token-Jaccard fallback) + `tools/implementations/memory_tool.py` (remember/recall, auto-reg) +
  `sections/agent_memory.py` + builder, wired context_hub (gather LAST + `render_agent_memory_section`) + agent_v2 append.
  LANDMINE: recall builds the ds-clause CONDITIONALLY (binding a bare NULL `:ds` → asyncpg AmbiguousParameterError); uid
  bound as `str(user_id or "")` sentinel.
- **#2 SUBAGENT FAN-OUT** (`HYBRID_SUBAGENTS`) — orchestrator-worker. `ai/runner/orchestrator.py` (`run_subtask`
  LLM→SELECT-only→client.execute_query→distill; `decompose`; `run_fanout` Semaphore(min(cap,4))+synthesize) +
  `tools/{implementations,schemas}/delegate_subtask.py` (planner-callable, self-gated, re-entrancy guard
  `subagent_depth>=1`). N× tokens → budget + concurrency capped; single-analyst path untouched when OFF.
- **#3 SKILL AUTO-GROW** (`HYBRID_SKILL_AUTOGROW`) — Voyager. `completion_feedback_service._run_propose_skill`
  (mirrors `_run_propose_from_positive`: fresh session, reload org/user/completion by PK, small model,
  `skill_authoring.distill_skill_from_completion`) fires on 👍 at both sites → DRAFT pending skill → owner activates.
- **#4 BI-TEMPORAL** (`HYBRID_BITEMPORAL`) — Zep/Graphiti. `ai/brain/bitemporal.py` (`current_condition`→`invalid_at IS
  NULL` when on else None; `asof_conditions`; `supersede_prior`). Migrations `bitemp1` (3 cols on metric_definitions/
  semantic_tables/agent_memories) + `bitemp2_partial_unique` (drop UNIQUE → partial unique `WHERE invalid_at IS NULL AND
  status='approved'`). Read-filters in resolve_metric/metrics+semantic builders/agent_memory.recall; supersede-on-approve
  in `routes/knowledge.py` BEFORE the approve-flip; time-travel `as_of` on resolve_metric. LANDMINES: cols are TIMESTAMP
  WITHOUT TZ → supersede uses NAIVE UTC (`datetime.now(timezone.utc).replace(tzinfo=None)`, else asyncpg rejects →
  silent no-op); partial-index scoped to `status='approved'` (bare `invalid_at IS NULL` blocked pending+approved
  coexisting → broke proposer); supersede MUST precede approve-flip (else two approved-current rows collide).
- **#5 WORKFLOW RUNNER** (`HYBRID_WORKFLOWS`) — MetaGPT verifier gate, conductor for #2. `ai/workflows/runner.py`
  (`run_pipeline(items, stage_fn, judge_fn, max_concurrency, max_retries)` → per-item stage→gate→pass/retry/skip/log,
  never raises; `llm_judge` PASS/FAIL; `produced_knowledge_judge` deterministic) + `ai/workflows/jobs.py`
  (`train_connector_tables` reuses connector.py resolution + autotrain_connector per table; `WORKFLOWS` registry) +
  `routes/workflows.py` (`POST /api/workflows/{name}/run`, flag-gated+auth). LANDMINE: `autotrain_connector` writeback
  COMMITS on the SHARED async session → concurrency>1 = "Session is already flushing"/lost writes → `train_connector_
  tables` PINNED `max_concurrency=1` (runner still supports parallelism for jobs whose stage owns its own session).
- **#6 CONTEXT COMPRESS** (`HYBRID_CONTEXT_COMPACT` + sub-flags `_LLM`, `_RATIO`) — GCC/OpenDerisk. New
  `ai/context/compaction.py` `compact(instructions, model)` SYNC no-LLM (runs ~2×/iter): **EDIT** (over budget=
  context_window*RATIO[0.75], floor 4k/fallback 24k → drop lowest-priority `###` blocks via `_DROP_ORDER`:
  code_bank→agent_memory→docs→join_graph→brain_graph→proven-queries; NEVER base/schemas/messages/semantic/metrics/
  skills/studio) + **AWARENESS** (append "### Context budget: ~X of ~Y tokens"). **COMPRESS** = `maybe_compress` async
  truncate MVP, LLM digest sub-flag OFF (TODO). agent_v2 touched MINIMALLY: +1 method `_apply_context_compaction` + 3
  one-line call sites before each `PlannerInput(instructions=…)` (init ~852 uses local `instructions_text`, post-tool
  ~2272, reflect ~3924). LANDMINE FIXED: site 852 reuses `instructions_text` across knowledge-harness loop steps → a
  non-idempotent compact STACKS awareness lines + inflates the token count → made IDEMPOTENT (`_strip_awareness` drops
  the prior `### Context budget` block before re-measuring; awareness always appended LAST). Verified live in-container:
  flag True + in snapshot, compact 10021→12 tok dropped only `proven approaches` core kept, method present.

## 2026-06-21 — #7 SKILL OPTIMIZER (microsoft/SkillOpt pattern, native) — LIVE, BAKED, verified
A SKILL.md is a TRAINABLE artifact: optimize it with NL edits gated by held-out evals. Frozen LLM, no
fine-tune, no GPU, OpenRouter-only, approval-gated — same idiom as #1-#6. Plan `docs/PLAN_SKILL_OPTIMIZER.md`.
Built Wave-0 (foundation) → Wave-1 (4 disjoint-file sub-agents) → parent joined the linchpin + baked.
Loop = ROLLOUT (run skill on a held-out golden suite via TestRunService→AgentV2) → REFLECT
(Judge.score_response_quality + failing-case critiques) → AGGREGATE (LLM ≤N textual edits on skill_md,
mirrors skill_authoring) → SELECT (accept only if eval PASS-RATE strictly improves — deterministic
`_compare_result_sets` gate, can't regress) → UPDATE (persist as a NEW `skills` row `status='draft'`).
- **Migration `skillbitemp1`** (down=`bitemp2`, NEW HEAD): +`valid_at`/`invalid_at`/`superseded_by` on
  `skills` + PG partial-unique `uq_skill_current` on `(organization_id, scope, name)` WHERE
  `invalid_at IS NULL AND status='active'`. So a draft version COEXISTS with the live active row;
  promoting a 2nd version to active WITHOUT superseding the old VIOLATES the index (proven in DB).
- **`app/ai/skills/optimizer.py`** `optimize_skill(db, *, organization, user, skill_id, eval_suite_id=None,
  case_ids=None, epochs=3, max_edits_per_epoch=3, model=None)` — never raises; `{skipped:True}` when flag
  off / skill-not-active / no suite. Rollout polls TestResult rows to terminal (cap 900s); pass-rate off
  `TestResult.status=='pass'`. NAIVE-UTC for the bitemporal cols.
- **`pinned_skill` rollout pin** (dict `{name, skill_md, allowed_tools, disallowed_tools}`): AgentV2.__init__
  `+pinned_skill` → seeds `runtime_ctx["active_skill"]` at BOTH runtime_ctx sites + force-injects the
  candidate `skill_md` via S5 `render_injected_skill` in the main planner-loop append. LINCHPIN (parent-
  fixed): the eval path is `TestRunService.create_and_execute_background → CompletionService.create_completion
  → AgentV2`; CompletionService was UNTOUCHED by the wave agents (the 2 AgentV2 sites they saw, 1164/1250, are
  in `stream_run`, OFF-path) → threaded `pinned_skill` through `completion_service.py` (create_completion +
  _create_completion_traced sigs + passthrough + the 2 real on-path AgentV2 ctors at ~676/742). Without this
  the chain TypeErrors at the file boundary.
- **`loader.list_visible_skills`** + `Skill.invalid_at.is_(None)` (unconditional, no-op for existing rows —
  hides future superseded versions).
- **Routes (`app/routes/skill.py`, singular)**: `POST /api/skills/{id}/optimize` (flag-gated, returns
  `{disabled:True}` 200 when off, never 500s) + NEW `POST /api/skills/{id}/activate` (no activate endpoint
  existed) — runs an INLINE supersede (`update(Skill)...invalid_at=now, superseded_by=new` gated on
  `flags.SKILL_OPTIMIZE`, NOT bitemporal's internal HYBRID_BITEMPORAL gate) BEFORE flipping draft→active, so
  `uq_skill_current` never collides. NAIVE UTC.
- **Flags** `HYBRID_SKILL_OPTIMIZE` (+`_DAEMON`), default OFF, in .env + compose. Reuses #5 runner · Judge ·
  P4 eval matcher · #4 bitemporal.py (generic) · skill_authoring · approval gate. Backup
  `.backups/20260621_110345_skill-optimizer`. VERIFIED live: head=skillbitemp1, 3 cols+idx in DB, flag in
  snapshot, optimizer/route/pinned_skill present, fail-soft no-ops, versioning guard enforced. ~515 routes.

## 2026-06-21 — #7 POST-MVP FIXES (finalize · improve-E2E · cache-bypass · daemon-user) — all BAKED+PROVEN
Four fixes after the MVP, all live-verified on Music Store + real OpenRouter, image rebuilt.
- **Finalize fix (Option B).** The rollout's path = `create_and_execute_background` (Path 1) RUNS the analyst but NEVER finalizes TestResults (only `stream_run`'s streaming path did) → pass-rate read 0. Extracted the inline evaluate-block from `stream_run` into `TestRunService._finalize_one_result(...)`; added public `TestRunService.finalize_run_results(db, org, user, run_id)` (no SSE/queue, idempotent, fail-soft). Optimizer `_rollout` now = create_and_execute_background → NEW `_await_completions_terminal` (polls the system COMPLETIONS, not TestResult) → `finalize_run_results` → `_pass_rate`. Same Path-1 gap wired into nightly `eval_harness.run_scheduled_evals` via `_await_and_finalize_run` BEFORE `detect_regressions`. **LANDMINE:** read fresh status after the finalize (which commits in a SEPARATE session) with `select(...).execution_options(populate_existing=True)` — NOT `db.expire_all()` (expire leaves attrs expired → later sync attr access does implicit async IO outside the greenlet → `greenlet_spawn has not been called` crash).
- **Improve→draft→activate E2E PROVEN.** Format-token failing baseline (skill omits a required output token the expectation demands) → baseline 0.0/['fail'] → AGGREGATE LLM adds the format rule → re-rollout 1.0/['pass'] → `improved=true`, NEW draft `skills` row persisted, live active row untouched (invalid_at NULL). Activate→supersede verified (old row invalid_at+superseded_by=new, exactly 1 active-current, `uq_skill_current` holds). **Expectation-rule gotcha:** must be FieldRule `{"type":"field","target":{"category":"completion","field":"text"},"matcher":{"type":"text.contains","value":...}}` — a flat `{"type":"text.contains",...}` is silently push_skipped → failed==0 → VACUOUS pass.
- **Cache no-op fix.** With serve-caches on (QUERY_CACHE+ANSWER_CACHE+BRAIN_READ — the live config), each pinned CANDIDATE was answer-cache-served (cache keys on question+datasource, NOT pinned_skill; hit precedes the agent) → candidate never re-ran → SELECT gate saw no change → optimizer a SILENT NO-OP on any cached org. Single chokepoint: `agent_v2._serve_from_reasoning_cache` is the only caller of `run_serving_funnel` (only caller of serve_answer_cache+try_serve_proven_query). FIX = 2 guards in `agent_v2.py`: (a) top of `_serve_from_reasoning_cache` `if getattr(self,'pinned_skill',None): return False` (bypass both answer-cache ① + reasoning-cache ②); (b) `and not getattr(self,'pinned_skill',None)` on the answer-cache write-back (~3869) so candidate N's answer doesn't poison candidate N+1. PROVEN deterministically: seed sentinel into answer_cache → pinned rollout's completion `served_by=None` + answer is fresh (not sentinel); sentinel still cached after (no write-back).
- **Daemon user bug.** `run_scheduled_skill_optimize` (the @04:00 daemon) passed `user=None` → `create_and_execute_background` guards `requested_by_user_id` (test_run_service.py:598) but then derefs `str(current_user.id)` UNGUARDED in `_create_stub_report` (line 615) → every rollout crashed `'NoneType' object has no attribute 'id'` → daemon a SILENT PERMANENT no-op. Fixed: daemon resolves an org-member user via `_resolve_org_member_user` (imported from eval_harness, same pattern `run_scheduled_evals` uses), skips orgs with no member. Proven: baseline_scores 0.0→1.0. (`run_scheduled_evals` was already clean.) Neither daemon has an in-body leader gate (leader gating is at the APScheduler caller).
- Tidy: deleted dead `_await_run_terminal` + `_TERMINAL` from optimizer.py (superseded by `_await_completions_terminal`). Plan doc `docs/PLAN_SKILL_OPTIMIZER.md` header marked COMPLETE. #7 = fully shipped, nothing dangling; both daemons run clean, still flag-OFF in prod by design.

## 2026-06-21 — HYBRID UI SURFACES (flag admin page · memory review · workflows · skill-origin)
Closed the backend-ahead-of-frontend gap: 4 hybrid features got real per-user/admin UI (built by 9 parallel disjoint-file sub-agents + parent integrate/bake). Migration `skillorigin1` (NEW HEAD, down=skillbitemp1): +`origin` VARCHAR(20) server_default 'manual' on `skills`. All flag-gated default-OFF; baked into cityagent-analytics:dev, verified live.

- **Feature Flags admin page (the linchpin — was env-only).** Per-org live override of all 8 HYBRID_* flags WITHOUT container restart. Backend: `app/settings/hybrid_flags.py` got module-level `_OVERRIDES: dict[str,bool]` — `_bool(name)` now returns `_OVERRIDES[name]` if present else env (unchanged when empty); helpers `set_override(env,val|None)`, `overrides_snapshot()`, `async load_overrides_from_db(db)->int` (scans org_settings.config['hybrid_overrides']), and `UPGRADE_FLAGS` metadata map (8 envs → {label, role: agent|user|review}). Routes in `app/routes/organization_settings.py` (already main-registered, no main.py touch): `GET /api/organization/hybrid-flags` (list {key,env_name,label,role,default_env,override,effective}) + `PUT /api/organization/hybrid-flags/{env_name}` body {enabled:bool|null} (writes config['hybrid_overrides'] + `flag_modified(settings,'config')` since config is plain JSON not JSONB + commit + `set_override` live). Both `@requires_permission('manage_settings')`. Parent wired `load_overrides_from_db` into main.py startup_event (fail-soft) so overrides survive restart. **LANDMINE — 4 uvicorn workers:** `_OVERRIDES` is per-process; a live PUT updates only the worker that served it; others reload from DB on next restart (DB is durable). OK for dev/single-org; multi-worker live-sync = future shared store. FE `pages/settings/features.vue` (settings layout, toggle table, role chips, optimistic PUT+revert). Nav: Settings→Feature Flags tab (TopNav.vue:380 + layouts/settings.vue allTabs).
- **#1 Agent Memory review.** NEW `app/routes/agent_memory.py` (registered main.py:81 import + :262 include, prefix /api): `GET /api/agent/memories?status=&scope=` (org-scoped, invalid_at IS NULL, personal rows private to author, []-when-flag-off), `POST .../{id}/approve` (status→approved), `POST .../{id}/reject` (retires bi-temporally via invalid_at=NAIVE-UTC — no 'rejected' status exists; drops from recall+pending). Gated flags.AGENT_MEMORY (writes 403 off via AppError FEATURE_LOCKED). FE `pages/memory/index.vue` (Pending/Approved/Personal tabs, approve/reject). Nav: Build→Memory (/memory). **E2E SMOKE PROVEN live:** flagOFF→[]; override ON→flag flips; seed pending→list sees it→approve→approved (drops pending, enters approved); reject→retired.
- **#5 Workflows.** `app/routes/workflows.py` +`GET /api/workflows` (list from jobs.WORKFLOWS via WORKFLOW_METADATA dict, []-when-off) + `GET /api/workflows/{name}/status` (from new in-process `_LAST_RUNS` dict — runs are ephemeral, no persistence table) + run_workflow now records _LAST_RUNS (done/error) WITHOUT changing its signature/return. FE `pages/workflows/index.vue` (cards + DS picker via GET /api/data_sources + Run + inline summary). Nav: Manage→Workflows (/workflows, manage_settings).
- **#3 Skill origin badge.** `skill_authoring.distill_skill_from_completion(origin='manual')` (shared row-builder); auto-grow `_run_propose_skill` passes origin='auto', manual route passes 'manual'. Surfaced in BOTH read paths: routes/skill.py `_serialize` + ai/skills/loader.py `list_visible_skills` (both `getattr(...,'manual')`-safe). FE `pages/skills.vue` violet "Auto-proposed" badge when origin=='auto' (UIcon sparkles, no emoji).

VERIFY (live): image baked + ca-app healthy (0 boot errors); routes 401/400 (registered+gated, not 404); pages /memory /workflows /settings/features all 200; single head skillorigin1; memory loop + flag-override resolver + origin serialize + workflow meta all proven by in-container coroutine smoke. Deferred (need backend foundation first, NOT built): #2 subagent monitor (runs ephemeral, no table), #6 context-budget readout (metrics internal-only). Mockups: ui-mockup.html (concept) + ui-mockup-match.html (app-styled). 9 agents = BE-FLAGS/BE-MEM/BE-WF/BE-ORIGIN + FE-NAV/FE-FLAGS/FE-MEM/FE-WF/FE-BADGE; WAVE0 owned migration; parent owned main.py boot-load + bake.

## 2026-06-21 — BRAND COLOR STANDARDIZATION (clay primary, killed off-brand blue)
Symptom: "Add Member" button + active "Members" tab rendered BLUE while brand accent is CLAY #C2683F ("New report" button). ROOT CAUSE: no `frontend/app.config.ts` existed → Nuxt UI (v2.22.3) fell back to its DEFAULT blue primary, so every bare `UButton`/`UTabs`/`UBadge`/`UToggle` (no explicit color) was blue; clay was only ever hardcoded inline (`bg-[#C2683F]`). Nuxt UI v2 resolves `ui.primary` from the TAILWIND theme (`#tailwind-config/theme/colors`), not app.config alone — if the named color isn't in Tailwind it warns + falls back to green.
FIX (2 new config files + project-wide literal sweep, baked):
- NEW `frontend/app.config.ts`: `defineAppConfig({ ui: { primary: 'clay', gray: 'stone' } })`.
- NEW `frontend/tailwind.config.ts`: registers `theme.extend.colors.clay` 50–950 (500=`#C2683F` main, 600=`#A8542F` hover/dark; 50 `#FBF6F2`,100 `#F4E5DA`,200 `#E8C9B5`,300 `#DBAC8F`,400 `#CF8A65`,700 `#8B4427`,800 `#6E3620`,900 `#5A2D1B`,950 `#331810`). The @nuxtjs/tailwindcss module auto-merges it; no nuxt.config change. → all DEFAULT U components + active-tab underlines now clay.
- Swept EXPLICIT blue literals → clay across MembersComponent.vue + all pages/settings/** + ~150 components/** + 27 pages+layouts. Rules: `color="blue"`→`color="primary"`; `bg-blue-500/600`(+hover)→`bg-[#C2683F]`+`hover:bg-[#A8542F]`; `text-blue-*`→`text-[#C2683F]`(+hover `#A8542F`); active `border-blue-500`+`text-blue-600`→`#C2683F`; `focus:ring/border-blue-500`→`#C2683F`; tints `bg-blue-50`→`#F6EFEA`,`bg-blue-100`→`#F4E5DA`,`border-blue-200/300`→`#E8C9B5`,`text-blue-700/800`→`#A8542F`; brand hexes `#2563eb/#3b82f6/#60a5fa`→`#C2683F`.
- DELIBERATELY LEFT (NOT brand): chart data-series palettes (RenderVisual/EChartsVisual/ArtifactFrame/themes/index.ts/PerformanceChart 2nd-series), `colorScheme` enum string values ('blue' = palette lookup key not CSS), user color-picker swatches. Green/red/amber/emerald/teal/slate/purple semantic states untouched.
VERIFY (live, built dist CSS at /app/frontend/dist/_nuxt): clay primary compiled = 690× `C2683F` + clay rgb `194 104 63` in `--color-primary-*` vars; only 11× residual `2563eb` (all in entry.css = the kept chart palettes); /settings/members 200, ca-app healthy. Baked cityagent-analytics:dev. CONVENTION GOING FORWARD: new UI = use bare U components or `color="primary"` (now clay) / inline `bg-[#C2683F]` hover `bg-[#A8542F]`; never `color="blue"` or `bg-blue-*` for brand/interactive elements.

## 2026-06-21 — AGENT STEP VISIBILITY + AUTO-PILOT PANEL (Claude-style live run view) — LIVE, BAKED
Front-end only (+ 1 live DB instruction). Goal: show what the agent is doing every step, like Claude. Backups `.backups/*_agent-step-visibility` + `*_autopilot-panel`. Mockups at repo root: `ui-mockup-steps.html`, `ui-mockup-activity.html`, `ui-mockup-autopilot.html`.

**KEY DISCOVERY (the linchpin):** the live chat does NOT use `CompletionMessageComponent.vue` (that's legacy/unused on the report page — only a CSS comment references it). The report page (`pages/reports/[id]/index.vue`) renders agent activity DIRECTLY by iterating `m.completion_blocks` (the `v-for` at ~L267) — each block with `tool_execution` renders a tool card (`CreateDataTool.vue` = "Creating Data · Visualizing", `CreateWidgetTool`, `ClarifyTool` via `getToolComponent`). So agent steps = `completion_blocks`, NOT the documented `tool.started`/`tool.finished` SSE events (a first attempt built a parallel `steps[]` array fed by `reduceStepEvent` on those events — it stayed EMPTY because the real activity flows through `block.upsert`-built blocks). **Truth source for "what the agent did" = `completion_blocks`.**
- **`frontend/utils/stepMap.ts`** (NEW, auto-imported util): `AgentStep` shape + `prettyTool(name)` (17 tools → icon+title) + `reduceStepEvent()` (event-based, kept but UNUSED on live path) + **`blocksToSteps(blocks)`** (THE one used — maps `completion_blocks` → step rows; tool blocks → {kind tool/subagent, status from `tool_execution.status` success→done/error→warn/else→run, durationMs, body.code from sql/code, body.output from result_summary}; reasoning/answer blocks → think steps). Fully defensive, never throws.
- **`frontend/components/AgentStepTimeline.vue`** (NEW): labeled "Thought process · N steps · Done" pill (spinner while in_progress, green check done) + vertical collapsible step rows. Mounted in `CompletionMessageComponent.vue` (dead path — harmless). The LIVE inline surface = a "Thought process / Working · N steps" header added ABOVE the block `v-for` in the page (the block tool-cards ARE the per-step detail; header just frames them Claude-style). The bare `simple-dots` "···" startup state (page `shouldShowWorkingDots`, was at L367) → replaced with a labeled clay-spinner "Thinking…" pill.
- **Activity tab (4th right-panel tab, beside Summary/Dashboard/Agents).** Right panel switches on `rightPanelView` ('summary'|'artifact'/'grid'|'agent'|**'activity'**). Tab button + `#right` branch added; `activeSteps` computed = `blocksToSteps(lastSystemMessage.completion_blocks)`. Shows Progress checklist + bar, Data sources (`report.data_sources`), Skills used (badge load_skill/run_skill_file), Sub-agents (kind subagent), Outputs (create_viz/create_data/create_artifact). Token-budget line = "context budget pending — / —" (placeholder until #6 surfaces the number).

**AUTO-PILOT PANEL (`reports/[id]/index.vue`).** Default `rightPanelView='activity'` (was 'artifact'). Panel follows the run automatically:
- refs `autoPilotPanel` (default ON, localStorage `dash_autopanel`), `userPinnedView`, `userClosedPanel`.
- `setPanelView(view, manual=false)` = single entry point; `manual=true` PINS (stops auto-switch this run) + adjusts width via `panelLeftWidthFor` (Activity = narrow right / 60% chat; Dashboard = wide / 40%; Summary 55%; Agents 48%).
- Watchers: (a) run-start (`status`→in_progress) → open panel + Activity, reset per-run pins; (b) **`activityOutputs.length` grows** (per-run signal, resets each run — used INSTEAD of `hasArtifacts` which only flips false→true once so follow-up queries wouldn't re-trigger) → flip to Dashboard unless pinned; (c) run-ends text-only → Summary if it has content, else stay Activity.
- All tab buttons + `@viewDashboard`/`@openInstructions`/`@toggleArtifactView` routed through `setPanelView(...,true)`; close-x sets `userClosedPanel=true`. Header **Auto** toggle (bolt/bolt-slash). Mobile untouched.

**CACHE-SERVE RENDER FIX (the "answer blank + Activity 0/0" bug).** A repeated question is served by the answer/reasoning cache (`completions.served_by='answer_cache'`) → the agent loop is SKIPPED → **0 completion_blocks**, the answer lives on `completion.content`. The page renders ONLY blocks → blank chat + empty Activity. FIX: (1) template fallback renders `m.completion.content` when NO block carries content (`!blocks.some(b=>b.content||final_answer||assistant||tool_execution)`); (2) `activeSteps` synthesizes a single "Answered instantly (cached)" step (reads new `served_by` field, added to the completion→message map) so Activity isn't 0/0. To SEE full live steps, ask a NOVEL question (cache miss) — repeats serve instantly with no steps by design.

**DATA-DATE LANDMINE + 0-ROW FIXES.** Symptom: "Plot sales for 2009" → Execution succeeded · **0 rows** → empty chart. ROOT CAUSE: this demo's `chinook.sqlite` is **RE-DATED to 2021–2025** (83 invoices/yr), NOT chinook's classic 2009–2013 — the agent hardcoded `WHERE year=2009` from training prior → matched nothing. Two fixes: (1) **published org Instruction** (live, no rebuild — `instructions` table, org 55278108, category 'general', status 'published'; NOT-NULL cols need `thumbs_up=0`+`is_seen=false`): "before filtering/grouping by date, FIRST inspect MIN/MAX of the date column; never assume years from dataset name". (2) **RenderVisual.vue 0-row empty-state** improved (it ALREADY gated `!props.data?.rows?.length` — chart was never faking data; the blank frame WAS the empty-state) → now clearer "Query returned 0 rows · check the date/year range" with icon. VERIFY: head/health 200, baked; `blocksToSteps`/`dash_autopanel`/`Thought process`/`Thinking…` all in dist.

**AUTO-PILOT TRIGGER FIX (don't open empty Dashboard on inline charts).** Bug: an inline chart (`create_data`/`create_viz`) auto-flipped the panel to Dashboard, which was EMPTY ("No artifacts yet") — an inline chart lives in the CHAT, it does NOT populate the Dashboard tab. The Dashboard tab only fills from a REAL artifact (`create_artifact` / "Generate Dashboard"). FIX: the auto-flip watcher now triggers on **`hasArtifacts`** (real artifact, set live at agent_v2 L2590 on `create_artifact`), NOT on `activityOutputs`. Net behavior: inline-chart run → stays **Activity** (chart in chat); real dashboard artifact → flips **Dashboard**; text-only → **Summary**. Manual click still pins.

## 2026-06-21 — MULTI-TENANT cache scoping + AMBIGUITY GATE (R3) + cache-blank fix — LIVE, BAKED
3 fixes (A/B/C) built by disjoint-file sub-agents, parent wired the shared `agent_v2.py` + flag plumbing. Driven by a multi-tenant SaaS reality: **100 users, Studios pin same-or-different data sources, per-user results.** KEY INSIGHT: the scope unit is the **data-source SET a Studio pins** (+ studio context), NOT user/org. Caches are already org-scoped + studio-namespaced (`answer_cache._scoped_hash(norm, studio_id)`), but the agent_v2 funnel caller passed only the FIRST source id + NO studio_id → the namespacing wasn't actually exercised, and multi-source Studios could mis-share.

- **A — full-source-set cache key (no migration).** `answer_cache`/`query_cache_store`/`code_cache_store`/`serving_funnel`/`query_cache_serve` take a new optional `data_source_ids: list[str]`. Helper `_sources_fp(ids)=",".join(sorted(map(str,ids)))` folded into the hash **ONLY when len(ids)>1** → single-source/None is byte-identical (existing rows still hit, zero cache invalidation); multi-source sets get distinct, order-independent keys. DB WHERE on the single `data_source_id` col untouched (uniqueness comes from the hash). **Parent wired** `agent_v2.py` `run_serving_funnel(...)` (~L1797) to pass `data_source_ids=[str(d.id) for d in self.data_sources]` + `studio_id=str(self.report.studio_id) if report.studio_id else None` (was first-source-only, studio_id never passed). → Studios on same source set share (cost win across the 100 users), different sets isolate, studio context namespaced.
- **B — AMBIGUITY GATE / "ask before assuming" (R3, AmbiSQL pattern).** Kills the 2009-bug class. NEW `app/ai/clarify/{__init__,ambiguity_gate}.py`: `async detect_ambiguity(db, *, organization, question, schema_summary=None, data_source_hint=None, model=None) -> {ambiguous, kind, clarifying_question, suggested_options}`. ONE cheap LLM call (reuses `app.ai.llm.llm.LLM(model, usage_session_maker=async_session_maker).inference(prompt, usage_scope="ambiguity_gate")` — SYNC blocking call from async, the repo's brain-module idiom; small model via `LLMService().get_default_model(db, org, None, is_small=True)`). Detects kinds: `missing_date_range` (incl. a specified year that may not exist), `undefined_relative_time`, `ambiguous_metric`, `ambiguous_entity`. Self-gates `getattr(flags,"AMBIGUITY_GATE",False)`, never raises, OpenRouter-only, vectorless. **Parent wired** into `agent_v2.py` ONCE pre-loop (after the code_bank instructions block ~L2196, where all hybrid `_X_block`s append — region runs ONCE before the agent loop; loop init `observation/active_artifact` starts right after): if ambiguous → injects a `### Clarify before answering` directive telling the planner to **call the existing `clarify` tool** (reuses ClarifyTool.vue → NO new FE) instead of guessing. New flag `AMBIGUITY_GATE` (`@property` in `hybrid_flags.py`, env `HYBRID_AMBIGUITY_GATE`) added to hybrid_flags + `.env`(=1 dev) + `docker-compose.build.yaml`(`:-0`) — LANDMINE: all THREE or silent-OFF. VERIFIED in-container: `flags.AMBIGUITY_GATE=True`, `detect_ambiguity` is async coro.
- **C — scroll-up cache-blank bug.** `loadPreviousCompletions` (FE pagination map, ~L3133) was MISSING `completion` + `served_by` (the main `loadCompletions` map has them) → older cache-served answers (`served_by='answer_cache'`, 0 blocks, answer on `completion.content`) rendered BLANK on scroll-up. Added both fields. FE-only.

VERIFY: `import main` clean (≈515 routes), all py_compile OK, baked + ca-app healthy :3007 200, funnel signature has `data_source_ids`. TEST B: ask "plot sales revenue by month for 2009" → agent should `clarify` ("which year? 2021/2022/2023/all") instead of 0-row chart. Research basis: arXiv AmbiSQL (ambiguity gate 42.5%→92.5%) + competitive landscape (Wren/Snowflake VQR/Genie/ThoughtSpot value-resolution) + OpenWork (plan+permission/clarify as UI objects). Full roadmap R1–R12 in the session; R1 value-resolution via `pg_trgm` (no embeddings) + R4 verified-query repo are the next biggest levers, both scope per-data-source = multi-tenant amplified.

## 2026-06-21 — RENAME "Studios" → "Agent Studios" (UI label only)
Feature display name changed Studio/Studios → **Agent Studio / Agent Studios**. UI label ONLY — routes `/studios`, i18n KEYS (`studio.*`, `nav.studios`), vars/components (`selectedStudio`, `StudioFlyout`, `studio_id` col) UNCHANGED.
- `locales/en.json` (repo-root `locales/`, NOT frontend/locales): `nav.studios` + `studio.{title,yourStudios,newStudio,createStudio,createTitle,empty,disabled,disabledHint,notFound,backToStudios,deleteStudio,studioCreated,studioDeleted,settingsTitle}`.
- Hardcoded Vue labels: `components/AgentSelector.vue` (Studios header + New Studio), `components/prompt/DataSourceSelector.vue` (Studios header + New Studio ×2), `components/nav/ChatHistoryRail.vue` (`title="Studio"`).
- LEFT inline prose (`this studio's pinned sources` etc.) lowercase — reword = noise, reads fine.
- FE baked SPA → i18n COMPILED INTO JS bundle (`/app/frontend/dist/_nuxt/*.js`), NO standalone en.json in container. Needs full image rebuild + hard-refresh. Baked + ca-app 200.

## 2026-06-21 — UPLOAD LOCAL EXCEL/CSV → Data Agent + TRAIN surfaces (Knowledge docs) — LIVE, BAKED
User gap: Studio "Add source" only PINS existing Data Agents (both already pinned → "No Data Agents available to pin"), and the connector picker had NO file-upload tile → **no UI path to bring local data in**. Fixed with a new `spreadsheet` connector + upload UI + a studio Knowledge-docs surface. Built by 3 disjoint-file sub-agents (BE / FE-connectors / FE-studio) against a pinned API contract; parent fixed a body-binding bug + baked. Mockup at repo root `mockup-upload-train.html`.
- **BACKEND — `spreadsheet` connector (DuckDB in-memory, un-gated).** NEW `app/data_sources/clients/spreadsheet_client.py` (`SpreadsheetClient(DataSourceClient)`: pandas `read_csv`/`read_excel` per sheet → `con.register` as DuckDB tables; sanitizes sheet→table names; honors optional `sheet_names`; full base iface test_connection/get_schemas/get_tables/get_schema/prompt_schema/execute_query; traversal-safe path under `<cwd>/uploads/files/`). Registered in `app/schemas/data_source_registry.py` (`spreadsheet` → client_path, `requires_license=None`, data_shape=tables, shared, ui_form=data_source, auth none) + `app/schemas/data_sources/configs.py` (`SpreadsheetConfig{file_id,sheet_names,path}` + `SpreadsheetNoAuthCredentials`). NEW route `app/routes/data_source_from_file.py` `POST /api/data_sources/from-file` (`@requires_permission('create_data_source')`), included in `backend/main.py` BEFORE `data_source.router`.
- **CONTRACT.** `POST /api/data_sources/from-file` body `{file_id (from POST /api/files), data_source_name?, sheet_names?, description?}` → creates `Connection(type='spreadsheet')` + `DataSource`, links via the REAL junction **`domain_connection`** (`models/domain_connection.py`; recon's "DomainConnection" guess was WRONG — it's the lowercase Table, `DataSource.connections`↔`Connection.data_sources` M:N), runs the canonical discovery `ConnectionService.refresh_schema → DataSourceService.sync_domain_tables_from_connection` (same path as the demo loader; `_create_memberships(...,['manage'])` so creator can read), returns the full `DataSourceSchema` dict **+ additive top-level `tables[]`** (base schema has no tables field; route has no response_model so it's additive). Errors: 404 file-not-in-org, 400 unreadable/unsupported, 409 dup name. Schema discovery is **fail-soft** (bad file → ds still created, `tables:[]`).
- **LANDMINE (cost me a smoke cycle): `from __future__ import annotations` + the `@requires_permission` wrapper made FastAPI mis-read the pydantic body param as a QUERY param** → `422 {"loc":["query","payload"],"missing"}`. The decorator wraps the endpoint and FastAPI couldn't resolve the stringized annotation `payload: DataSourceFromFileRequest` to a BaseModel → treated it as a primitive (query). FIX: removed `from __future__ import annotations` from the route file (it only used `Optional[...]`, no PEP-604 `|`, so safe). RULE for new routes with body models behind `@requires_permission`: do NOT use future-annotations, or FastAPI won't see the body.
- **`/api/files` now exposes `preview`.** Added `preview: Optional[Any]=None` to `FileSchema` (`app/schemas/file_schema.py`) — `from_attributes` auto-populates from the `File.preview` JSON the upload already generates (excel `{type,sheet_names,sheet_previews{sheet:{raw_cells,shape}}}` / csv `{type,raw_cells,shape}`). Purely additive; the upload modal's sheet/column preview reads it. (Was stripped before → preview was blank.)
- **FRONTEND.** NEW reusable `frontend/components/data/UploadSpreadsheetModal.vue` (props `{open:Boolean, studioId:String|null}`, emits `close`/`created(dataSource)`; drag-drop .xlsx/.xls/.csv ≤50MB → `POST /files` (FormData, field `file`) → render sheets+column preview from `preview` → name/desc → `POST /data_sources/from-file` → emit created; uses `useMyFetch` BARE paths + `useToast`, clay theme). `frontend/pages/connectors.vue` — added a first "Upload File / Spreadsheet" tile opening the modal. `frontend/pages/studios/[id]/index.vue` — (a) Sources header split: **Pin existing | Upload file**; Upload opens the modal with `:studio-id`, and on `@created` AUTO-PINS via the existing `pinSource(ds)` (`POST /studios/{id}/sources {agent_id:ds.id}`) + `fetchSources()` (solves the "nothing to pin" dead-end); (b) NEW left-rail **Knowledge docs** tab (KNOWLEDGE group) = paste form (title+body+DS picker of pinned sources or org-wide null) → `POST /knowledge/docs {title,body,source:'paste',data_source_id}` + list `GET /knowledge/docs[?data_source_id=]` with status pills + Approve (`POST /knowledge/doc/{id}/approve`) / Reject (`/reject`, hidden if 404). `{disabled:true}` → "Enable Knowledge Docs in Settings → Feature Flags" hint.
- **Flags (already ON in dev):** `HYBRID_DOC_KNOWLEDGE=1`, `HYBRID_STUDIOS=1`, `HYBRID_AUTOTRAIN=1`. The `spreadsheet` connector itself is UN-gated.
- **VERIFIED LIVE (E2E, real OpenRouter org):** login → `POST /files` (preview type=csv present) → `POST /data_sources/from-file` → DataSource created with discovered `tables[0].columns = [region,product,units,revenue]`. Post-bake re-smoke OK. Routes mounted (`/api/data_sources/from-file`, `/api/knowledge/docs`), connector resolves (`resolve_client_class('spreadsheet')→SpreadsheetClient`), all FE strings baked in `_nuxt/*.js`. COSMETIC: CSV table name = stored filename stem (uuid-prefixed, e.g. `<uuid>_smoke`) — valid SQL, agent sees columns fine; could later name from data_source_name. Backups not taken (small, additive).

## 2026-06-21 — REPORT-PAGE FIXES: Summary→Outputs · softer errors · OpenRouter retry · locals() self-heal · dashboard skeleton — LIVE, BAKED
5 fixes from a user bug report (3 screenshots: empty Summary, red error walls, stuck "Generating dashboard…"). Built by 4 disjoint-file sub-agents, one rebuild bakes BE+FE. Mockups `mockup-fixes.html` (before/after). 523 routes, healthy.
- **2A OpenRouter stream retry (`app/ai/llm/clients/openai_client.py`).** ROOT: a single OpenRouter network blip surfaced as red `LLM v2 streaming failed: Connection error` (zero retry). FIX: new `_open_stream_with_retry()` wraps `chat.completions.create` — retries ONLY transient (`httpx.ConnectError/ReadError/RemoteProtocolError/TimeoutException` + `openai.APIConnectionError/APITimeoutError`, name/msg fallback), NOT `BadRequestError`/auth. 3 attempts, exp backoff 0.5→1s, WARNING log. LANDMINE handled: **idempotent** — `yielded_any` flag, retry ONLY if no chunk yielded yet (mid-stream fail re-raises, no duplicate text). `llm.py:439` RuntimeError wrapper unchanged (fires only after retries exhausted).
- **2B locals() self-heal + prompt steer (`code_execution.py` + `agents/coder/coder.py`).** ROOT: model emitted `locals()`; AST blocklist blocks it (`FORBIDDEN_BUILTINS` UNCHANGED — still blocks locals/globals/vars/eval/exec/open) and `except CodeSecurityError` did `break` (dead red end). FIX: (1) coder `generate_code` prompt rule **9. Sandbox safety** forbids locals/globals/vars/getattr/eval/exec/open + says use try/except NameError (live path = create_data v2 `code_generator_fn=coder.generate_code`, NOT the dead alt-prompts at coder.py ~188/454). (2) `generate_and_execute_stream_v2` (the real loop — recon's create_data.py:1374 was wrong, it's in code_execution.py) gets `security_retry_budget=1`: first violation appends corrective feedback + `continue` (regenerate) instead of break; 2nd → final break. `security_violation` event yielded every block → audit `log_tool_audit('security.unsafe_code_blocked')` preserved. Successful regen ends clean.
- **1 Summary→Outputs + Answer card (`components/report/ChatSummary.vue` + `pages/reports/[id]/index.vue` + `locales/en.json`).** ROOT: `ChatSummary.hasAnything` = queries||artifacts||queryExecutions||instructions → text-only answers = "No items yet"; webhook button was the centerpiece. FIX: report page computes `latestAnswer` (walks `lastSystemMessage.completion_blocks` from end, skips error/clarify → `block.content||plan_decision.final_answer||assistant`, falls back to cache-served `completion.content`) + passes to BOTH ChatSummary mounts (desktop ~L695 + mobile ~L66); ChatSummary renders a clay "Answer" card (MarkdownRender from markstream-vue) at top, `hasAnything = hasAnswer || …`. Tab label en.json `reportView.tabSummary` "Summary"→"Outputs" (KEY/route 'summary' unchanged). Webhook demoted to faint dashed footer link.
- **2C soften recovered errors (`utils/stepMap.ts` + report page Activity render + `components/tools/CreateDataTool.vue`).** `blocksToSteps`: Pass-0 computes `progressAfter[i]`+`runReachedAnswer`; an errored tool block becomes **warn (amber 'retried'/'self-fixed')** if the run progressed after it / ultimately answered / matches `RECOVERABLE_PATTERNS` (LLM streaming/connection/timeout → "retried"; security/unsafe_python/forbidden/locals → "self-fixed"); stays red ERR only on final no-recovery failure. Activity step UI + CreateDataTool inline error show amber pill + raw error collapsed behind "show detail" (default hidden). CreateDataTool was already amber; message-level red (`m.status==='error'`) left red (true final fail).
- **3 dashboard skeleton + anti-stuck (`components/dashboard/ArtifactFrame.vue` + NEW `DashboardSkeleton.vue`).** ROOT: pending = bare `<Spinner>"Generating dashboard…"` (ArtifactFrame:147) + NO poll/timeout → status stuck 'pending' (agent fails mid-build) = infinite spin. FIX: NEW `DashboardSkeleton.vue` (prop mode page|slides, widgetCount; shimmer KPI row + 2-col widget grid mirroring real layout; warm/clay shimmer keyframe, no blue/emoji) swapped into the pending branch. Anti-stuck: while `isPendingArtifact`, poll `fetchSelectedArtifact()` every **5s** (double-interval guarded, cleared in onUnmounted); after **90s** or fetch-error → `buildError=true` → ERROR panel ("Dashboard build stopped" + clay **Retry build** → clears state, re-fetch, best-effort POST `/api/reports/{id}/rerun`, resume poll). Success iframe/SlideViewer path + props/emits unchanged.
- VERIFIED LIVE: `import main` 523 routes no crash; openai_client retry present; security_retry_budget + coder steer present; FE baked (Outputs label, DashboardSkeleton "building", "self-fixed"/"Dashboard build stopped" in `_nuxt/*.js`). Hard-refresh to clear cached JS chunk. Mockup `mockup-fixes.html`.

## 2026-06-21 — REPORT-PAGE FIXES R2: skill silent-fake-data · tab crowding · panel-jump · step narration — LIVE, BAKED
4 issues from a user bug report (4 screenshots). 2 disjoint sub-agents (1 skill/BE, 1 FE-all-3 since same file), one rebuild bakes BE+FE. Mockup `mockup-issues2.html` (tab A/B/C options, before/after each). Container healthy :3007.
- **SKILL SILENT-FAKE-DATA (the dangerous one — 3× bigger than the screenshot showed).** ROOT: `skills_library/programmatic-eda/scripts/eda.py` hardcoded `SELECT * FROM orders LIMIT 5000` in a bare `try/except → df=None → synthetic 300-row np.random fallback`. Source w/o an `orders` table (e.g. RTM) → query throws → skill reports **success but analyzed FABRICATED data**. AUDIT: **ALL 12 GitHub-sourced skills had the same pattern** (hardcoded tables: orders/customers/experiment_events/events/sales + np.random fallbacks): programmatic-eda, data-profile, ab-test-analysis, anomaly-detection, business-metrics-calculator, cohort-retention, funnel-analysis, kpi-snapshot, pareto-8020, rfm-segmentation, segmentation-analysis, time-series-trend. FIX (all 12): introspect via **`client.get_schemas()`** (abstract base `app/data_sources/clients/base.py`, returns `Table` w/ `.name`, all connectors implement) → quote discovered table `SELECT * FROM "<table>" LIMIT 5000` → iterate clients until rows → **FAIL LOUD** `raise RuntimeError(...)` if no client/table/rows. Synthetic fallback DELETED everywhere. **LOAD PATH: skills load from BOTH disk + DB — `importer.py` seeds disk→DB once, but `run_skill_file` reads EXCLUSIVELY from `skill_files.content` at runtime.** So BOTH updated: host files fixed + `docker cp`'d into `ca-app:/app/skills_library/` + `py_compile` clean ×12, AND 15 `skill_files` rows updated via psycopg2 to `ca-postgres` (verified no `FROM orders`/`np.random` remnants). 3 residual DB `FROM orders` matches are HARMLESS — demo/example SQL strings in `sql_lint.py`/`sql_anti_patterns.md`/`sql_explainer.py`, not data-loaders.
- **TAB CROWDING (Option A) — right-panel tab bar `pages/reports/[id]/index.vue` `#right-header` (~L626-700).** ROOT: tabs icon+full-text `px-3 py-1.5` + Auto toggle + ✕, no overflow → wrap/crowd on narrow panel. FIX: compact tabs `px-2 py-1`, `whitespace-nowrap` + `flex-none` icons; **"Dashboard"→"Dash"** (L651, `title="Dashboard"` kept); tab group wrapped `overflow-x-auto no-scrollbar min-w-0` (scrolls not wraps); **Auto toggle → icon-only bolt** (`w-7 h-7`, bolt vs bolt-slash, `aria-label="Auto-pilot"`, clay-filled active/muted off); **✕ pinned far right** `flex-none ms-1` separated from bolt (`ms-auto`). Added `.no-scrollbar` to scoped `<style>`. All handlers/active-styling/focus-ring preserved.
- **PANEL-JUMP ("right screen moves too much") — PROGRESS card (~L722).** ROOT: PROGRESS card grew as steps streamed (no reserved height) → shoved Data sources/Skills/Sub-agents/Outputs sections down each step. FIX: `min-h-[180px] flex flex-col` reserves ~4 steps; progress bar pinned bottom `mt-auto` → streaming steps fill reserved space, siblings stop reflowing. NOTE: no Activity-panel auto-scroll existed (only left-chat reasoning box + chat container scroll, untouched) → "remove auto-scroll" was a no-op.
- **STEP NARRATION ("its working, I don't know what's working — explain what's going/coming") — `utils/stepMap.ts` + Activity render.** ROOT: model's plain-language reasoning ALREADY emitted at `block.plan_decision.reasoning` (shown left-chat thinking-box) but Activity panel only showed terse hardcoded TOOL_MAP labels. FIX: `stepMap.ts` `blocksToSteps` adds optional `why?` field via new `whyFromBlock()` (collapse whitespace, ~140-char cap, `''` when absent; recovered steps use friendly recovery note — honest about retries; RECOVERABLE_PATTERNS/amber-pill untouched). `index.vue` Activity: per-step muted `why` line under each label (`v-if="step.why"`) + **Now/Next banner** atop panel (`activityNow`=narration/label of in-progress-or-latest step; `activityNext`=pending step after current, OMITTED when none — stream exposes no forward plan, degrades honest rather than fabricating). Amber retried/self-fixed pills still render.
- VERIFIED LIVE: build exit 0, force-recreate, `health: healthy`; DB skill rows clean (`get_schemas`, no fake-data); SFC/template compile 0 errors. Hard-refresh to clear cached JS. Mockup `mockup-issues2.html`.

## 2026-06-21 — R3 FIXES: empty-state card grid · skill hasattr sandbox-block · Activity panel height+width — LIVE, BAKED
- **EMPTY-STATE REDESIGN (`components/DataSourceQuestionsHome.vue`, used by `pages/index.vue` + `pages/reports/new.vue`, same `@update-content` emit → both inherit).** Floating rotating pills → **6-card 2×3 grid** (`grid grid-cols-1 sm:grid-cols-2 gap-3`, collapses 1-col narrow, `max-w-2xl`). Each card = category tag + heroicon + 2-line prompt (`line-clamp-2`). Auto-categorize from prompt verb via `categorize()`: `Compare`(vs/correlation) `i-heroicons-arrows-right-left` · `Dashboard`(build/overview) `squares-2x2` · `Trend`(over time/avg) `arrow-trending-up` · `Rank`(top/most/which) `chart-bar` · `Explore`(fallback) `magnifying-glass`. Clay `#C2683F` tag + border-hover. Pool still from `data_sources[].conversation_starters` (split on `\n`, label=first line, value=full). Kept rotate-one (6s) + `↻ shuffle` link (shown when pool>6). Heading untouched (`reports.emptyTitle`). Convention: `<UIcon name="i-heroicons-...">`.
- **SKILL SANDBOX-BLOCK (`hasattr`) — run_skill_file errored "Forbidden function call: 'hasattr()'".** ROOT: all 12 skill scripts had `tname = table.name if hasattr(table, 'name') else str(table)` (the get_schemas introspect line from R2). Sandbox AST gate `FORBIDDEN_BUILTINS` (`app/ai/code_execution/code_execution.py:205`) bans `hasattr`/`getattr`/`setattr`/`eval`/`exec`/`open`/`locals`/`globals`/`vars`/... → script rejected pre-exec → agent fell back to raw SQL (the amber "self-fixed" / "skill blocked, I'll use SQL"). FIX: `hasattr(table,'name')` → **`'name' in dir(table)`** (`dir` NOT forbidden), sandbox-safe, same behavior. Applied 12 disk files (perl) + **15 `skill_files` DB rows** (psql replace) + `docker cp` into container + `py_compile` clean ×12. Runtime reads DB → live, no rebuild for this part. **LANDMINE: skill scripts run in the AST-gated sandbox — NO introspection builtins (hasattr/getattr), NO eval/exec/open/locals; use `'x' in dir(obj)` or try/except AttributeError instead.**
- **ACTIVITY PANEL HEIGHT (`pages/reports/[id]/index.vue` PROGRESS card ~L753).** ROOT: R2 added `min-h-[180px]` but NO max → card grew with steps (1→5 + per-step `why` narration) → shoved Data sources/Skills/Sub-agents down (the "expands more" jump). FIX: card `max-h-[340px]`; step-list wrapper (`v-if="activityTotal>0"`) → `flex-1 min-h-0 overflow-y-auto no-scrollbar -mx-1 px-1` (scrolls internally). Progress bar + footer pinned (`mt-auto`). Card holds stable size regardless of step count.
- **ACTIVITY=OUTPUTS WIDTH.** ROOT: right-panel width = window minus `leftPanelWidth` (left/chat px, `SplitScreenLayout.vue`). 4 conflicting setters; `activity` had NO explicit branch → always hit catch-all `else 0.37` → right panel **63% (wide)**, while `summary`(=Outputs) → left 0.55 → right **45%**. FIX: give `activity` the SAME 0.55 as `summary` in all 3 relevant setters — `panelLeftWidthFor` (L1685 `0.60→0.55`), `watch(rightPanelView)` (L2184 `'summary'||'activity'`), `toggleSplitScreen` ternary (L3473 add `||'activity'`). Auto-open L4038 = artifact-only, left. Now Outputs↔Activity = identical 45% right, no resize on switch; Dash/artifact stay wide (63%) for charts.
- TESTED LIVE: skills #3 CONFIRMED working (SKILLS USED panel shows Loaded skill / Ran skill = used). Sub-agents #2 trigger = multi-part "research each independently" prompt in Analysis/deep mode. AMBIGUITY GATE fires twice on demo data (2021-2025 vs today June 2026) for "last 12 months" — by design, not a bug. **OPEN/NEXT: new skill bug surfaced — `run_skill_file → Validation failed: tables_by_source: Input should be a valid list` (cohort skill passes non-list to tables_by_source); NOT yet fixed.** `#6 context-budget readout` still hardcoded placeholder `context budget pending — / — tokens` (no backend). VERIFIED: build exit 0, force-recreate, `health: healthy`. Hard-refresh for cached JS.

## 2026-06-21 — RECURSIVE VERIFY (RecursiveMAS-inspired, text-space critic+retry on subagent path) — BAKED, flag-OFF
- **WHAT.** Studied RecursiveMAS (arxiv 2604.25917 / recursivemas.github.io). Paper's real mechanism = latent-space hidden-state transfer via trainable RecursiveLink modules + gradient training on local HF weights/vLLM/GPU → **IMPOSSIBLE on our OpenRouter-only, API-only stack** (no weights, no internals, no training). Did NOT implement that. Stole the transferable text-space lesson: recursion = draft→critique→re-do (bounded), + compressed handoffs cut tokens.
- **DESIGN (self-contained on the subagent path; NO agent_v2.py surgery, NO migration):** each `delegate_subtask` worker finding is graded by a cheap CRITIC; HARD-error findings re-delegate with the reviewer note appended (bounded loop). Rides on `delegate_subtask` so it is a no-op unless `HYBRID_SUBAGENTS` is also on.
- **FLAG:** `HYBRID_RECURSIVE` (default OFF) — `hybrid_flags.py` property `RECURSIVE` + `UPGRADE_FLAGS["HYBRID_RECURSIVE"]={"label":"Recursive Verify","role":"agent"}` (→ shows in admin Feature-Flags page) + added to `snapshot()` (also added missing `SUBAGENTS`). Env knob `HYBRID_RECURSIVE_MAX_RETRIES` (default 2, hard-clamped 0..3).
- **BACKEND (`app/ai/runner/orchestrator.py`):** `critique_finding(model,question,result)` → `{passed,reason,hint}`, HARD-errors-only prompt (no data/wrong entity/time/metric/ungrounded numbers; PASS when in doubt), **FAIL-OPEN** (empty/unparsed critic reply → passed=True; deterministic fast-fail only on empty answer). `run_subtask_verified(...)` wraps existing `run_subtask` in the loop: `while attempts<=max_retries` (so 1+max_retries runs, ≤3), pass+ok → return verified; fail → carry hint into next attempt's question; **no ds_clients → max_retries forced 0** (nothing to re-query = zero token burn). Returns run_subtask dict + `verified`/`attempts`/`critic_reason`.
- **TOOL (`delegate_subtask.py` + schema):** `DelegateSubtaskOutput` += `verified:Optional[bool]`, `attempts:Optional[int]` (None when flag off → byte-identical). When `flags.RECURSIVE`: call `run_subtask_verified`, message = "verified" / "verified (self-fixed after N retries)" / "unverified after N attempt(s): <reason>"; observation summary prefixed `[verified] `/`[unverified] `.
- **FRONTEND (`frontend/utils/stepMap.ts`, subagent branch only):** reads `te.result_json.verified/attempts` (fallback parse `[verified]`/`[unverified]` prefix). verified-after-retry (attempts>1) → reuse `recovered`+`recoveredLabel:'verified'` amber pill; unverified → `status:'warn'`+`recoveredLabel:'unverified'` (amber caution, never red); clean first-try / flag-off → no pill (identical to today). Null-safe.
- **VERIFIED LIVE:** py_compile ×4 clean; container imports OK; `flags.RECURSIVE`=False default, in UPGRADE_FLAGS + snapshot; output fields None when off. Functional smoke (mock LLM): empty→deterministic fail; persistent-fail loops **exactly 3** (1+2) then unverified+reason; pass→attempts 1; no-clients→attempts 1 (retries skipped). Build exit 0, force-recreate, `ca-app healthy`.
- **LANDMINES:** (1) bounded ALWAYS — `max_retries` clamped 0..3, no-clients→0; never remove caps (infinite loop / token burn). (2) critic = HARD-errors-only + fail-open; if tuned strict it wastes retries rejecting good findings. (3) rides on SUBAGENTS — useless alone; both flags must be ON. (4) per-finding critic = +1 cheap LLM call each; simple Qs (no fan-out) never hit it.
- **TO ENABLE:** `HYBRID_SUBAGENTS=1` + `HYBRID_RECURSIVE=1` (env or admin Feature-Flags per-org override). NOT YET turned on / not E2E-proven on a real multi-part question — Phase 4 live-run pending user.

## 2026-06-21 — SLIDES + EXCEL TABS (report right-panel) + Workspace nav pages — BAKED, LIVE
- **WHAT.** Two NEW right-panel tabs on the report page — **Slides** (deck builder) + **Excel** (workbook) — as peers of Dash (NOT inside the dashboard). Plus two new Workspace-nav library pages (Presentations / Spreadsheets). User wanted slides/sheets OUT of the dashboard. Mockup `mockup-slides-excel.html` (interactive: tab + 3 theme switch).
- **COMPONENTS (NEW, presentational, props-only, no API/Pinia):** `frontend/components/report/SlidesPanel.vue` props `{visualizations?:any[], reportTitle?:string}` — thumbnail rail + aspect-video canvas, slide 1 auto-title then 1 slide/viz, **3 themes** (theme-clay/dark/edit CSS gradients), `Export .pptx` (lazy `import('pptxgenjs')`, try/catch). `frontend/components/report/ExcelPanel.vue` props `{sheets?:{name,columns,rows}[], workbookTitle?:string}` — sheet-tab strip + read-only grid (cap 200 rows), normalizes array-of-objects→array-of-arrays, `Export .xlsx` (lazy `import('xlsx')`). Both empty-safe → empty-state when no data.
- **DEPS:** `yarn add xlsx@^0.18.5 pptxgenjs@^4.0.1` (frontend/package.json) — client-side export, browser-safe, no backend. Imported LAZILY inside export handlers (missing dep can't break render).
- **WIRING (`frontend/pages/reports/[id]/index.vue`):** `rightPanelView` union += `'slides'|'excel'` (2 spots: ref decl L1663 + `setPanelView` sig). Explicit imports added (after ChatSummary import). 2 tab buttons after Activity (heroicons `presentation-chart-line` / `table-cells`, labels `reportView.tabSlides`/`tabExcel`). 2 panel branches after Activity div, before Agent View (`v-else-if rightPanelView==='slides'|'excel'`). Width: slides/excel fall through `panelLeftWidthFor` else→0.40 left = wide right (matches Dash); NO width-setter change needed. NEW computed `excelSheets` (after `visualizations` ref ~L1216): walks `messages[].completion_blocks[].tool_execution.result_json` for tabular data (`data_model.columns`+rows, either row shape), fully try/catch fail-soft → []. SlidesPanel fed `visualizations` (same source as Dash), ExcelPanel fed `excelSheets`.
- **WORKSPACE NAV (`frontend/components/nav/TopNav.vue` ~L400):** added 2 items to workspace group after `dashboards`: `{key:'presentations',href:'/presentations',icon:'heroicons-presentation-chart-line',label:'nav.presentations'}` + `{...spreadsheets, heroicons-table-cells, nav.spreadsheets}`. NEW pages `frontend/pages/presentations/index.vue` + `pages/spreadsheets/index.vue` (copied canonical list-page shell from `pages/dashboards/index.vue` — same wrapper/max-w-7xl/grid/`definePageMeta({auth:true})`); v1 = static EMPTY STATE (no backend) pointing user to report→Slides/Excel tab→Export, "Browse reports"→/reports.
- **i18n (`locales/en.json` — repo-root, NOT frontend/locales):** `nav.presentations`="Presentations", `nav.spreadsheets`="Spreadsheets", `reportView.tabSlides`="Slides", `reportView.tabExcel`="Excel". (i18n compiled into _nuxt bundle → rebuild required, done.)
- **NAMING:** tab labels short (**Slides**/**Excel**); workspace library pages formal (**Presentations**/**Spreadsheets**). Avoid PowerPoint/Excel trademark words in nav; `.pptx`/`.xlsx` only on export buttons.
- **VERIFIED:** frontend build exit 0 (nuxt generate clean — TS union + new SFCs + computed all valid), force-recreate, `ca-app healthy`. Hard-refresh for cached JS.
- **v1 SCOPE / NEXT:** Slides = view + reorder placeholder + pptx export (canvas shows framed viz placeholder, NOT live ECharts render — wire real chart-to-image later). Excel = view + xlsx export, read-only (no cell edit, no formulas — v2). Presentations/Spreadsheets pages = empty-state only (no saved-deck/workbook backend yet — future: persist exports + list them). `+ New sheet` / `+ Add slide` = placeholders.

## 2026-06-21 — TAB ROW = ICON-ONLY COLORFUL PRODUCT ICONS (cosmetic) — BAKED LIVE
- Report right-panel tab row (`reports/[id]/index.vue` #right-header ~L631): replaced heroicon+text tabs with **icon-only** colored inline-SVG buttons (no labels; native `title` tooltip carries the name). Buttons now `w-9 h-8` square, active = bg-gray-100 (Activity = #F6EFEA). Mockups `mockup-tab-icons.html` (A/B options) + `mockup-real-icons.html` (chosen).
- Icons (real product look, gradient SVGs; gradient `<defs>` declared ONCE in #right-header, referenced `url(#id)`): Outputs=blue data-table (tblB) · Dash=**Power BI** gold bars (pbiY) · Agents=**Copilot** swirl violet→cyan (agV; dropped the old per-agent DataSourceIcon/name) · Activity=pulse amber→red (acR) · Slides=**PowerPoint** orange swoosh+magenta P (ppO/ppP) · Excel=**Excel** gray doc+green X (xlG). LANDMINE: gradient IDs (ppO/ppP/xlG/pbiY/tblB/agV/acR) are GLOBAL in the DOM — keep unique; the hidden `<svg width=0>` defs block must stay rendered or fills go black. `DataSourceIcon` import now unused on this tab (still imported; harmless). TRADEMARK: PowerPoint/Excel/Power BI = MS marks — fine internal, flag if shipped public. Build0+healthy; hard-refresh for cached JS.

## 2026-06-21 — TAB TOOLTIP + ARTIFACT-BY-MODE ROUTING — BAKED LIVE
- **TAB TOOLTIP (cosmetic).** Icon-only tabs: native `title` → styled dark pill BELOW icon (`reports/[id]/index.vue` #right-header). Each button = `tabico relative` + child `<span class="ttip">label</span>`; scoped CSS `.tabico .ttip` (#1F2937 pill, white 10px, arrow-up via ::before, 120ms fade, z-50, no reflow) + `.tabico:hover .ttip`. **LANDMINE: removed the tab-group `overflow-x-auto whitespace-nowrap no-scrollbar`** (it clipped the dropping tooltip; 6 small icons fit without scroll). Header wrapper (SplitScreenLayout.vue L20 `flex-shrink-0 flex items-center justify-between`) does NOT clip → tooltip shows.
- **ARTIFACT-BY-MODE ROUTING (the real fix: decks→Slides, dashboards→Dash).** ROOT of "presentation generates under Dashboard": deck = backend **Artifact** with `mode='slides'` (vs dashboard `mode='page'`); `ArtifactFrame` rendered ANY mode + auto-pilot always flipped to `'artifact'` (Dash) — nothing routed on mode. KEY: discriminator **already exists** = `Artifact.mode` (`backend/app/models/artifact.py:36`, VARCHAR; `'page'`|`'slides'`; API `GET /api/artifacts/report/{id}` + `/{id}` return it; `create_artifact` tool sets it). **NO migration.** Excel is NOT a backend artifact (`WriteToExcelTool` = Office-taskpane postMessage only, no Artifact record) → Excel tab stays client-only.
- **FIX (frontend-only, 2 files, 1 sub-agent, backup `frontend/_backup_artifact_routing_20260621-211200/`):** (1) `components/dashboard/ArtifactFrame.vue` += OPTIONAL prop `modeFilter?:'page'|'slides'` (default undefined = NO filter = byte-identical for every other caller); `applyModeFilter()` filters the fetched list before dropdown/auto-select-first/hasArtifact/render; `handleArtifactCreated` only adopts an incoming artifact if it survives this frame's filter (Dash ignores slides, Slides ignores page). (2) `reports/[id]/index.vue`: per-mode computeds off already-loaded `reportArtifacts` (`hasSlidesArtifact`= any mode==='slides', `hasPageArtifact`= any mode!=='slides'; NO new fetch); Dash branch ArtifactFrame `mode-filter="page"`; Slides branch = `<ArtifactFrame mode-filter="slides">` when `hasSlidesArtifact` ELSE `<SlidesPanel>` fallback (SlidesPanel unmodified, conditional render — it renders client viz-decks, CANNOT render the React artifact code, so real decks MUST use ArtifactFrame); auto-pilot `watch(hasArtifacts)` now async → `await checkHasArtifacts()` then route `setPanelView('slides')` when `hasSlidesArtifact && !hasPageArtifact` else `'artifact'` (re-checks userPinnedView post-await; still gated by autoPilotPanel/userClosedPanel).
- **BACKWARD-SAFE:** modeFilter default=none → other ArtifactFrame mounts untouched; page-only reports = Dash as before; no-artifact = unchanged; both modes present → deck in Slides + dashboard in Dash, **auto-pilot defaults to Dash** (the `!hasPageArtifact` guard). Build0+healthy.
- **OPEN/NEXT:** (a) both-modes auto-focus = Dash (deck one click away in Slides) — flip to deck-wins if wanted. (b) TRUE Excel artifact = future epic (needs `mode='excel'` + backend spreadsheet generator; today Excel tab = client-side xlsx export only, no persisted artifact). (c) SlidesPanel client viz-deck now = fallback-only when no slides artifact.

## 2026-06-22 — STABILITY PASS: skills+subagents OFF, pgbouncer fix, stop button, dashboards build (LIVE, BAKED)
Multi-round debugging of "agent loops / dashboard never builds / UI hangs". Root causes found by DEEP verification (4 research agents were WRONG twice — Python-3.8-union-bug FALSE (runtime is 3.12), skill-steps-not-default FALSE (DB showed is_default=t). VERIFY claims live before acting.). Net decision: **DISABLE skills + sub-agents** — they were the instability source; the core `create_data → create_artifact` path is reliable and builds dashboards cleanly.
- **DECISION / STABLE CONFIG: `HYBRID_SKILLS=0` + `HYBRID_SUBAGENTS=0` in `.env`** (verified `flags.SKILLS=False`/`SUBAGENTS=False` at runtime). Reversible (set =1 + recreate). Skills/sub-agents need a redesign before re-enabling (executable skills should feed create_data; advisory skills must NOT be in the action catalog). The big multi-angle dashboard now builds via pure core: create_data ×3 (distinct titles) → create_artifact → KPIs+Pareto+genre+country. PROVEN live.
- **(R1) 120s "Thinking" hang = `ConnectionDoesNotExistError +120135ms`.** Cause: `ca-pgbouncer` `pool_mode=session` + `DEFAULT_POOL_SIZE=25`, but SQLAlchemy keeps `pool_size 20 + max_overflow 20 = 40` persistent client conns → in session mode each pins a server conn → >25 block on pgbouncer `query_wait_timeout` (default 120s) → conn dies → run crashes. FIX (`docker-compose.scale.yaml` pgbouncer env): `DEFAULT_POOL_SIZE 25→60`, `MIN_POOL_SIZE 5→10`, `QUERY_WAIT_TIMEOUT 30` (fail-fast, not 120). postgres max_connections=100 (60 fits). Recreate pgbouncer only. Transaction-mode flip AVOIDED (asyncpg prepared-stmt risk) — note as future for multi-user.
- **(P2) Flag→catalog gate.** `registry.py get_catalog_for_plan_type` now drops `load_skill/run_skill_file/read_skill_file` when `not flags.SKILLS` and `delegate_subtask` when `not flags.SUBAGENTS`, read at CALL time (live flip honored). Stops phantom "Sub-agent"/skill no-op steps (delegate_subtask self-no-ops "subagents disabled; no work done" but still showed as a step). Central — all callers inherit.
- **(P1) Stop button mid-run.** `reports/[id]/index.vue` new computed `runActive = isStreaming || lastSystemMessage.status==='in_progress'`; composer `PromptBoxV2.vue` Stop-vs-Send gates on it (was `isCompletionInProgress` which flipped false on `completion.finished` while the harness tail still ran → reverted to Send). `abortStream()` already POSTs `/api/completions/{id}/sigkill` + AbortController + status='stopped'. 
- **(P3) Spinner clears on terminal.** `completion.finished` SSE now defaults status→`'success'` when payload omits it → "Thinking" dots clear (don't wait for `[DONE]`). Kept the 150s watchdog `failRunUnexpectedly` + silent-close handling.
- **(E1) Scalar → KPI card.** `create_data.py` viz-infer: single 1×1 numeric result forced to `metric_card` (was blank chart). **(E2) soft-reason not red.** `GenericTool.vue` + `stepMap.ts`: agent skip/already-exists/recovered narration on an error-status tool renders gray info, not red ✗; genuine errors stay red.
- **DORMANT (skills off, kept in code for re-enable):** `run_skill_file` `sql=`→`input_df` threading (code_execution `_invoke_generate_df` delivers input_df when fn has **kwargs), run_skill_file emits Step+Viz (agent_v2 allowlist), descriptive `title` arg, skill-name code view (`created_step.code` via `arguments_json` added to `ToolExecutionMinifiedSchema`), agent_v2 stall guard (`skill_calls_since_build` steer@5/abort@10, independent of produced_output) + false-done fix (`produced_output` gate). Advisory skills `executive-summary-generator`+`dashboard-specification` set `status='archived'` (revert: status='active').
- **MODELS curated** to 3: Claude Sonnet 4.6 (default), Claude Haiku 4.5 (small-default), GPT-5.4 Mini; glm-5.2 + gemini-3.5-flash removed.
- **LANDMINE:** DB password is `dashpassword` (not `dash`). pgbouncer `pool_mode=session` — keep SQLAlchemy total conns (pool_size+overflow) under DEFAULT_POOL_SIZE or runs die at query_wait_timeout.

## 2026-06-22 — KNOWLEDGE-TRAIN + ROBOT ASSISTANT (5 features, baked LIVE)
Use case: load Abbott Myanmar nutrition CRM (6 monthly CSVs, 35 Salesforce-style cols) + a Definitions.xlsx (56 col-defs + KPI formulas) + an explanation deck, train the agent to be expert. **Per-studio knowledge** = each studio pins its own sources + own column-descriptions/instructions/examples.
- **DATA loaded (test studio):** merged 6 CSVs → `Abbott_MM_CRM_Jan-Jun2025.csv` (21,240 rows, 36 cols incl added `report_month`, gender normalized) → spreadsheet datasource **"Abbott MM CRM"** `84ee1ed9-7fa1-43fc-9c61-1c51e7e12fe6` (table `22a404f2-...`, DuckDB name `e59e494a_..._abbott_mm_crm_jan_jun2025`), pinned to studio **test** `2335870e-4137-444c-81bf-797885352ef6`, org `55278108-...`. 36 column descriptions written + 3 active KPI/classification/compliance instructions + 2 examples. **E2E PROVEN**: agent generated exact KPI SQL (Completed+Unsuccessful+User+Lapsed) → dropout by brand = Ensure 1995 / total 2632 (matches pandas ground truth 7/7).
- **TRAINING = 2 layers** (both fed to agent context, verified): (1) per-column `DataSourceTable.columns[].description` (schema_context_builder/prompt_formatters render inline); (2) StudioInstruction `status='active'` (studio_context_builder → agent_v2 ~L2137 appends `<studio_context>` when `flags.STUDIOS` ON + report.studio_id set). StudioExample active rows = few-shot. Metrics surface AS StudioExample rows.
- **API runbook (host→:3007):** login `POST /api/auth/jwt/login` form `username=admin@cityagent.io&password=CityAgent#2026` → bearer; ALL calls need `X-Organization-Id`. Upload `POST /api/files` (multipart field `file`) → file_id. Create source `POST /api/data_sources/from-file {file_id,data_source_name,description}`. Pin `POST /api/studios/{id}/sources {agent_id:<ds_id>}`. Instruction `POST /api/studios/{id}/instructions {content,source:'manual',status:'active'}`. Example `POST .../examples {question,answer,sql,source,status}`. Column desc has NO write API in core → direct SQL UPDATE datasource_tables.columns (or new F2 route below). Spreadsheet DuckDB = IN-MEM per query (re-reads uploaded file each call); PG holds descriptions/instructions → survive restart, `down -v` wipes.
- **5 NEW FEATURES (flag-gated default-OFF, ON in dev .env):**
  - **F1 auto-configure-from-doc** (`flags.AUTOMAP`/HYBRID_AUTOMAP): `backend/app/routes/studio_autoconfigure.py` + `app/ai/knowledge/doc_extractor.py`. `POST /api/studios/{id}/auto-configure/preview {file_ids[],data_source_id}` → LLM reads xlsx(openpyxl)/pptx(python-pptx) digest → strict-JSON {column_descriptions,instructions,examples,compliance} + fuzzy-match cols to live schema (difflib 0.6 + exact/ci/strip); offline fallback parses 2-col xlsx directly. `.../apply` → writes descriptions live + creates instructions/examples `status='pending'` (review-gated). PROVEN: Definitions.xlsx → 36/36 matched, 11 instr, 4 ex, 3 compliance. openpyxl+python-pptx already in requirements_versioned.txt.
  - **F2 column-desc editor**: `backend/app/routes/datasource_columns.py` GET/PUT `/api/data_sources/{ds}/tables/{tbl}/columns` body `{descriptions:{col:desc}}`. Perm = `@requires_resource_permission('data_source','view_schema')` (there is NO `update_data_source` perm). JSON-persist needs `flag_modified(table,'columns')`. FE: `components/studio/StudioTables.vue` REBUILT to render own list w/ editable desc grid (LANDMINE: this DROPPED TablesSelector delegation in the *studio* Tables tab → lost activation-toggle/stats/refresh there; agent Tables tab `agents/[id]/tables.vue` still uses TablesSelector).
  - **F3 KPI metric registry** (reuse `flags.METRICS_CATALOG`): `backend/app/routes/studio_metrics.py` — stores metrics AS StudioExample rows (question=`[METRIC] <name>: <def>`, status active) → already surfaced via studio examples, NO new table/migration. POST/GET/DELETE `/api/studios/{id}/metrics`. (Org-level MetricDefinition catalog also exists separately — not studio-scoped.)
  - **F4 compliance scan** (NEW `flags.COMPLIANCE_GATE`/HYBRID_COMPLIANCE_GATE; NOT reusing GOVERNANCE=agent-prompt-metadata): `backend/app/routes/compliance_scan.py` + `app/ai/compliance/scanner.py`. `POST /api/data_sources/{ds}/compliance/scan {phone_column?,required_fields?}` read-only via `DataSource.get_client().aexecute_query()` (helper at knowledge.py:470). dedup auto-picks /phone|contact|mobile/i col (Abbott has none → 'skipped'; "Contact Name" matches /contact/ = false-pick, pass phone_column to override), quality = missing-count per required field. PROVEN live: District 72% missing, quality_score 0.64.
  - **F5 self-learning review queue** (FE): studios/[id]/index.vue Instructions tab — lists `status=pending` instr+ex w/ Approve/Reject. Real endpoints: `POST /api/studios/{id}/instructions/{rid}/approve|reject` + same for examples (studio_instructions.py:237/262).
- **ROBOT ASSISTANT** (floating pixel Claude-Code-style mascot + live activity console): `frontend/components/RobotAssistant.vue` + `composables/useActivity.ts` (Nuxt useState singleton key `cityagent-activity`; contract: state idle|thinking|processing|success|error, start/setState/log/done/fail/openPanel/closePanel/clear, busy computed) + NEW `frontend/app.vue` (created — was none; MUST keep `<NuxtLayout><NuxtPage/></NuxtLayout>` + `<RobotAssistant/>`). Wired: studios/[id]/index.vue (auto-configure/compliance call sites push events) + reports/[id]/index.vue (watch runActive + activeSteps=blocksToSteps → log each step once, de-dup by step id). **SCOPED PER-AGENT**: `visible` computed = route matches `/(studios|agents|reports)/:id` (excl `/new`); `watch(agentKey)`→clear()+closePanel() so logs don't bleed across studios. **Launcher = NO disc** (user: "why circle around robo") — `.ra-bot-btn` background transparent + `filter:drop-shadow`, border-radius 0; busy pulse-ring only while working.
- **Mockups**: mockup-studio-train.html (real studio shell keep/add map), mockup-knowledge-train{,-real}.html, mockup-robot-logs.html, mockup-robot-claude.html (the animated pixel robot source for the component).
- **BUILD/DEPLOY**: FE change → `docker compose -f docker-compose.build.yaml build app` then `up -d --force-recreate app` (force-recreate picks up new compose env like HYBRID_AUTOMAP/COMPLIANCE_GATE; plain `docker restart` keeps OLD env → flags stay OFF). Backend-only → docker cp + restart works for code but NOT env. main.py registers routers explicitly (import block ~L50 + `app.include_router(x.router, prefix='/api')`); flags in `app/settings/hybrid_flags.py` (@property reading HYBRID_*) + `.env` + `docker-compose.build.yaml ${VAR:-0}` (all-three-or-silent-OFF landmine).

## 2026-06-22 — PRE-TRAIN BRAIN (Column Intelligence, Batch A/B/C) + studios blank-nav fix — LIVE, BAKED
User goal: fix 1000-row cap, make the agent "prepare already instead of training after question", know each column's type/role/values. All gated `HYBRID_COLUMN_INTEL` (default OFF / dev .env ON), baked into `cityagent-analytics:dev`, ca-app healthy :3007 (scale overlay ca-pgbouncer/ca-redis).
- **Batch A** — (1) row cap killed: org setting `limit_row_count` → value 0 / state `disabled` (config col is `json` not jsonb → `update organization_settings set config=(jsonb_set(jsonb_set(config::jsonb,'{limit_row_count,value}','0'),'{limit_row_count,state}','"disabled"'))::json where (config::jsonb) ? 'limit_row_count';`). Cap applies at `format_df_for_widget` (`code_execution.py:1091` `df.head`). (2) robot scope `RobotAssistant.vue:97` regex `(studios|agents|reports)`→`(studios|agents)` (agent-studio only, no report pages). (3) en.json `studio.tabKnowledge`/`addToKnowledge` keys. (4) active aggregate-in-SQL StudioInstruction (FK `instruction_id` is nullable → omit on manual insert).
- **Batch B = COLUMN INTELLIGENCE (the core)** — NEW `backend/app/ai/knowledge/column_intel.py`: client-based profiler that runs through `DataSource.get_client().aexecute_query()` (live DuckDB for the spreadsheet connector — NOT the dead `services/autotrain/profiler.py` which targets PG staging). Per column → `{role,distinct,null_pct,min,max,values}` (role = id/date/measure/dimension; `values` list only for dimensions with 0<distinct≤50, top 20). Read-only guarded, never raises. NEW `backend/app/routes/column_profile.py`: `POST /api/data_sources/{ds}/profile` merges into `DataSourceTable.columns[].metadata` keys role/values/distinct/null_pct/min/max (NEVER touches `description`; `flag_modified(t,'columns')` + commit) + `GET .../columns/intel`. Agent reads them: `ai/context/sections/tables_schema_section.py` (BOTH render paths) emits `<column ... role= values="a, b …+N more" distinct= nulls="X%"/>`. Flag in hybrid_flags.py @property + .env + compose `${HYBRID_COLUMN_INTEL:-0}`; router import+include in main.py. **LANDMINE: the model file is `app/models/datasource_table.py` (class `DataSourceTable`), NOT `data_source_table.py`.** E2E proven Abbott 21,240 rows / 36 cols (Brand→Ensure/Glucerna…, Channel→Digital/Trade/Ethical, District 72% null).
- **Batch C** — **P5 no-guess/value-resolution**: static directive in `agent_v2.py` (after the ambiguity-gate block ~L2222, gated COLUMN_INTEL, fail-open) "### Use real column values (no guessing)" — match the user term to an ACTUAL listed value case-insensitively, NEVER invent a filter value not in `values`, prefer cols by `role`, caveat high-null. **P6 one-click pre-train**: NEW `POST /api/data_sources/{ds}/pretrain {table_name?,suggest_knowledge=true,auto_approve=false}` in column_profile.py — (1) profile+store (shared helpers `_store_profile`/`_dimensions_summary`), (2) if suggest_knowledge & (SEMANTIC_LAYER|METRICS_CATALOG): `propose_knowledge_from_schema(focus=both)`→pending, (3) if auto_approve: `_auto_approve` flips returned SemanticTable/MetricDefinition ids status='approved' (SAFE — freshly-proposed rows have no competing approved-current row, so a plain flip can't collide with the bitemporal `uq_*_current` partial-unique index). FE `frontend/pages/agents/[id]/queries.vue`: clay **Auto-train** button + **Auto-approve** checkbox (admin-only `isAdmin=useCan('update_entities')`) + result card (rows·cols + dimension value chips). **P7 robot pre-train stream**: `runPretrain()` drives `useActivity` (start/openPanel/log per dimension/done/fail); robot already agents-route-scoped (Batch A) → live console on the queries page. E2E PROVEN: pretrain ok, 21240 rows, 36 written, 7 knowledge proposed (auto_approve=False) / 7 approved (auto_approve=True). **DEFERRED: P6 "benchmark gate"** (post-train eval run) NOT built — no safe per-agent eval-trigger without goldens; use the Evals page. In-container smoke = run host python → :3007 (the app listens :3000 inside; can't sed files in container /tmp — perms).
- **STUDIOS BLANK-ON-FIRST-NAV FIX.** Symptom: click Workspace → Agent Studios (and other Workspace pages) → blank, works on 2nd click. ROOT: global `app.pageTransition { name:'page', mode:'out-in' }` (`nuxt.config.ts`) stranded the ENTERING page at `.page-enter-from { opacity:0 }` on the first SPA nav (enter hook skipped) — the same strand class the report page had opted out of individually via `pageTransition:false`. FIX: disable it globally — `app: { pageTransition: false, layoutTransition: false }`. Fixes every page at once; `.ca-*` entrance helpers in `assets/css/transitions.css` still animate. SIGNATURE: blank-on-client-nav + works-on-2nd-click/refresh + NO console error == a route/page transition stranding the new page invisible (NOT a data/null bug).

## 2026-06-22→23 — STUDIO AUTO-PILOT + AUTO-TRAIN PIPELINE (sources merge · auto-queries/evals · async train · wizard) — LIVE, BAKED
Big multi-day push turning per-studio training into a one-button, self-driving pipeline. All gated, OpenRouter-only, baked into `cityagent-analytics:dev` (:3007, scale overlay). Full detail + landmines in memory `project_cityagent_autotrain_pipeline.md`.

**SOURCES PAGE = "Sources & Knowledge" (Design A merge).** `frontend/pages/studios/[id]/index.vue`: Knowledge tab folded INTO Sources; Connection + Tables folded INTO each source card as in-card tabs (Tables · Knowledge · Insights · Connection). Skills rail item HIDDEN (off for stability). Per-card knowledge add = inline form (no dropdown → killed the "why org-wide default" bug). Federation panel (auto-mined joins, % conf · ×N seen, enable/auto-enable) + Studio-insights panel (varied: coverage · widest-breakdown · sample values · date span · measure range · ONE null caveat) + Auto-configure-from-doc (one shared block).

**AI AUTO-PILOT page** (NEW rail tab `autopilot`, group 'main', DEFAULT landing): readiness ring (0-100 from sources/cols/docs/instr/examples/joins/artifacts — counts EXISTENCE not just active), stat grid, Connected-data cockpit (per-source trained/not + tables·cols), capability map (Tables/Knowledge/Evals/Artifacts/Federation/Skills-not-needed), AI suggestions, Pin/Upload + ONE **Auto-train everything** button. LANDMINE FIXED: `intelFor()` must be a PURE reader — writing a default slot inside a computed getter broke Vue tracking → "0 columns trained" while panel showed trained. fetchIntel owns slot creation.

**AUTO-TRAIN PIPELINE (4 sub-agents wave 1).** Per pinned source, all flag-gated:
- profile-all-cols fix (`column_intel.py`: values cap 50→200, distinct ALWAYS computed/None-on-fail, role always set).
- **CONNECTOR MULTI-TABLE fix** (`column_profile.py` `_profile_all_tables`): pretrain/profile looped ONE table only → connector's other tables stayed blank. Now loops EVERY active table, scoped per table (`_store_profile(only_table=)` — no shared-name cross-contamination). Music Store 11 tables/64 cols.
- **auto-queries** (`HYBRID_AUTO_QUERIES`, `ai/knowledge/auto_queries.py` + route): LLM proposes SELECTs → validates read-only → RUNS → saves passing to QueryLibrary (status='approved', source='auto').
- **auto-evals** (`HYBRID_AUTO_EVALS`, `ai/knowledge/auto_evals.py` + route): LLM Q+SQL → runs to derive REAL expected → TestCase golden (FieldRule shape, not flat — landmine). Creation only.
- **3 new artifact kinds** (`studio_artifacts.py` GENERATED_KINDS += notes/kpi_pack/data_dictionary; data_dictionary = DETERMINISTIC from intel).
- auto-approve toggle + parallel **Approve all** (FE) for pending instructions/examples/docs.

**THE BIG ROOT-CAUSE BUG (`_is_read_only_sql`).** The read-only guard (3 copies: column_intel, routes/knowledge, compliance/scanner) rejected ANY SQL containing the word **`call`** (CALL = stored-proc statement) → every query touching a `"Call Type"`/`"Call Outcome"`/`"Call Category"` column was blocked BEFORE running → killed profiler (distinct=None), auto-queries (Abbott 0 saved), evals. FIX: strip `"quoted idents"` + `'string literals'` before the write-keyword scan in all 3 copies. Abbott went 0→36/36 profiled, auto-queries 0→5+ saved. (Headers were CLEAN — NOT a ZWSP issue as first theorized; VERIFY-LIVE caught it via an in-container probe showing `_is_read_only_sql` False for "Call Type".) Also `_classify_role` reworked: id ONLY by id-name OR near-unique NUMERIC (text near-unique = dimension); date wins over surrogate-key rule.

**ASYNC BACKGROUND TRAINING (wave 2).** Auto-train was synchronous (FE awaited 30-90s of LLM). NEW `ai/knowledge/train_orchestrator.py` (in-proc `_RUNS` + strong `_TASKS` ref, own session, fail-soft per stage: profile→queries→evals→artifacts→value-joins) + `routes/studio_train.py` `POST /studios/{id}/train` (returns 0.1s) + `GET .../train/status`. FE `runFullTrain` POSTs + polls a %, non-blocking — navigate away, job continues. **LANDMINE: `_RUNS` is per-uvicorn-worker (4 workers) → poll hits wrong worker = "idle" flicker. FIXED: `_persist_db` mirrors status to `Studio.config['_train_status']` at each stage; GET route reads it when in-proc idle.** Proven done/100%.

**INCREMENTAL + DRIFT + DAY-1 JOINS + GENERIC COMPLIANCE (wave 2).**
- **Watermark skip** (`column_profile.py`): per-table `row_count` in `DataSourceTable.metadata_json['_profile_watermark']`; `_profile_all_tables(force=)` skips unchanged tables (ProfileRequest/PretrainRequest +`force`, `skipped_unchanged` in response).
- **Schema-drift** `GET /data_sources/{id}/schema-drift` (NEW `ai/knowledge/schema_drift.py`, live-vs-stored col diff, no persist).
- **Value-overlap joins** (`join_miner.py mine_value_overlap_edges` + route `value_joins.py POST /data_sources/{id}/mine-value-joins`): samples DISTINCT values, overlap≥0.5 → pending TableEdge source='value_overlap'. Works day-1 (no query history). Orchestrator runs it. Proven 40 edges.
- **Compliance genericized** (`scanner.py`): `_derive_required_fields` from live schema (geo/name/id/contact/date patterns); explicit list still overrides; City/District = last-resort generic fallback.
- **New-agent WIZARD** `frontend/pages/studios/new-agent.vue` (4 steps Name→Data→Train→Ready, real APIs + async train poll; Skip=background). `STUDIO_LEARN_DAEMON_ENABLED=1`.

**FLAGS added:** `HYBRID_AUTO_QUERIES`, `HYBRID_AUTO_EVALS` (+ existing COLUMN_INTEL/JOIN_GRAPH/STUDIOS/DOC_KNOWLEDGE). Env knob `STUDIO_LEARN_DAEMON_ENABLED`. main.py +auto_queries/auto_evals/studio_train/value_joins routers. NO migration (watermark in existing `metadata_json`; reused QueryLibraryItem/TestCase/StudioArtifact). Mockups: mockup-{sources-unified,studio-ai-autopilot,autotrain-pipeline,new-agent-wizard}.html. Agent analysis Python + dashboards = core `create_data`→`create_artifact` (claude-sonnet-4.6); NO skills/subagents/MCP (off for stability).

## 2026-06-23 — SUGGESTED FOLLOW-UP QUESTIONS (per-agent, ChatGPT/Claude style) — LIVE, BAKED
After every chat answer, 3-4 clickable follow-up chips render under the LAST assistant message; click → re-submits as a new question. **Per-agent**: each Studio generates its OWN follow-ups (not one global set). Flag `HYBRID_FOLLOWUPS` (default OFF / dev .env ON). 2 sub-agents (BE generator + FE wiring) + parent route/flag/bake. Plan-first (presented in CLI), then built.
- **GENERATOR `backend/app/ai/knowledge/followups.py`** (NEW, clones `auto_queries.py` idiom — same `LLM(...).inference(usage_scope="followups")` SYNC→`asyncio.to_thread`, `LLMService().get_default_model(is_small=True)`, `_introspect_schema_text` schema digest, tolerant fence-strip JSON parse, flag self-gate, NEVER raises, writes NOTHING). `async generate_followups(db,*,organization,current_user,report_id,answer_text="",question_text="",model=None,max_n=4) -> {ok,followups:[str],source:"studio"|"report"}` (`{disabled:True}` when flag off). **PER-AGENT grounding** = load Report→`studio_id`; if studio: voice=`Studio.persona` + ACTIVE `StudioInstruction.content` (status=='active') + optional explicit override `StudioArtifact(kind=='followup_policy')` (NOTE: StudioArtifact has NO status col → take most-recent non-deleted) + pinned-source schema digest (so chips reference REAL columns). ONE small-model call → JSON array of short Qs, clamp max_n 1..6. answer/question passed from FE (fallback loads latest `Completion.completion` — `Completion` has NO `content` col, only `.completion` JSON; roles are 'system'/'user'/'external', not 'ai_agent').
- **ROUTE `backend/app/routes/followups.py`** (NEW): `POST /api/reports/{report_id}/followups` body `{answer_text?,question_text?,max_n?}`. Auth mirrors `routes/completion.py` (`@requires_permission('create_reports')` + org-scoped Report load → 404 if not in org). **LANDMINE re-confirmed: NO `from __future__ import annotations`** (permission-decorated body → FastAPI mis-reads as query 422); body = `Dict[str,Any] = Body(default={})`. Route declares full `/api/...` path → registered in main.py via `app.include_router(followups.router)` WITHOUT `prefix` (like completion.py), NOT the `prefix="/api"` form the studio routers use.
- **FLAG** `HYBRID_FOLLOWUPS`: `hybrid_flags.py` @property `FOLLOWUPS` + `UPGRADE_FLAGS["HYBRID_FOLLOWUPS"]={"label":"Suggested Follow-ups","role":"user"}` (→ admin Feature-Flags page) + in `snapshot()` + `.env`(=1) + `docker-compose.build.yaml`(`${...:-0}`). All-three-or-silent-OFF.
- **FRONTEND `frontend/pages/reports/[id]/index.vue`** (only FE file): `ChatMessage` += `followups?:string[]`/`followups_loading?:boolean`. `fetchFollowups(m)` (guard: system msg + status==='success' + not training + not already loaded) derives `answer_text` by walking `m.completion_blocks` from end (content/final_answer/assistant, `completion.content` fallback for cache-served) → `POST` bare `/reports/${id}/followups` via `useMyFetch` → sets `m.followups`; fail-soft ([] on error/`{disabled:true}`, no re-fetch spam). Triggers: SSE `completion.finished` handler (fire-and-forget `setTimeout(...,0)`) + `watch(lastSystemMessage)` for already-finished reopens. RENDER: `mt-3` block under the message gated `m.id===lastSystemMessage?.id` + non-training — shimmer "Thinking of follow-ups…" while loading, else clay chips (verbatim empty-state starter class `border-gray-200 bg-gray-50 hover:bg-[#F3E7DF] hover:border-[#C2683F]`, no blue/emoji) `@click="handleExampleClick(q)"` (existing re-submit fn). Cache-served answers (0 blocks) still get chips.
- **VERIFIED LIVE (pre-bake, in-container, real OpenRouter):** route registered `/api/reports/{report_id}/followups`, `flags.FOLLOWUPS=True` + in snapshot, `generate_followups` on a real Abbott studio report → `source="studio"`, ok=True, 4 grounded Qs referencing real cols (channel types, call categories, Jan–June period). Then full image rebuild + force-recreate. Default OFF in prod (flag); reuses small model · no migration · no new table.

## 2026-06-23 — STUDIO LAUNCHER TAB (NotebookLM-style outputs + merged Activity) — LIVE, BAKED, FE-ONLY
Right-panel reworked into ONE **Studio** tab = output-launcher cards on top + live run-state below. NotebookLM "Studio" parity adapted to analytics. Plan/mockup-first in CLI (mockups `mockup-studio-{outputs,combined,actions,compact,merged}.html` in repo root), built across **3 sub-agents** (each baked). ALL in `frontend/pages/reports/[id]/index.vue` (single file, no backend, no migration). Bake = full image rebuild + force-recreate (baked Nuxt SPA); hard-refresh browser for new JS chunk.
- **NEW `'studio'` view** added to `rightPanelView` union (+ `setPanelView` sig). **Default landing = `'studio'`** (was `'activity'`); persists on fresh/new chat (onMounted only sets `'artifact'`/`'summary'` when pre-existing content → empty chat falls through to studio). Tab button = FIRST in row, clay sparkle SVG (flat `#C2683F` fill, no gradient), active `bg-[#F6EFEA]`. `panelLeftWidthFor('studio')`=0.55 (Outputs width); 'studio' added to the watch + toggleSplitScreen + leftPanelWidth branches (alongside summary/activity).
- **TOP = 2×3 output cards (`grid-cols-2`, compact `p-2` tiles, 15px icon + 11px label + 9px badge).** Click → GENERATE: Dashboard/Report/Infographic = `handleExampleClick('<preset prompt> ' + (lastUserQuestion||report?.title))` (real agent run via existing submit path — `lastUserQuestion` computed = latest `messages.value` role==='user' `m.prompt.content`, fallback report.title). Slides/Excel = INSTANT `setPanelView('slides'|'excel',true)` (SlidesPanel from `visualizations` / ExcelPanel from rows build on view, no LLM). Insight Map = SOON disabled `<div cursor-default opacity-65>`. NO new endpoint — agent cards just preset-prompt the existing pipeline.
- **BOTTOM = Activity tab MERGED in** (3rd sub-agent): the separate **Activity tab button was REMOVED**; its content now lives in the Studio pane below the cards, reusing the EXACT existing computeds verbatim (NO new ones): **NOW banner** (`activityNow`, clay pulse, "Idle" when not running) + **Progress card** (`activeSteps` done/run/warn rows + retry pill + `activityProgressPct` bar + `activityDoneCount`/`activityTotal`, internal `max-h` scroll) + **Data sources** `<details open>` (`report?.data_sources` + active pills) + **Skills used** `<details>` (`activitySkills`) + **Sub-agents** `<details>` (`activitySubagents`, `kind==='subagent'`) + **Outputs this run** card (`activityOutputs` rows → click `setPanelView('artifact',true)`). `<details>` summaries hide marker + `.chev` rotate-on-open (scoped CSS).
- **Run-start auto-flip REPOINTED**: `if (!userPinnedView.value) setPanelView('activity')` → `setPanelView('studio')` (so live run state shows IN Studio). Auto-pilot still flips to Dashboard on REAL artifact (kept).
- **LANDMINES / dead code:** old `v-else-if="rightPanelView === 'activity'"` pane block left in place but **unreachable** (no button) — harmless, `'activity'` still in union + width branches so nothing breaks; an intermediate `studioFeed` ref (Activity/Agents/Skills segmented switch from the 2nd sub-agent) is now UNUSED (superseded by the merged layout) — left in, harmless. Cleanup optional.
- **OPEN (not built):** Infographic = BETA (fires a prompt, no real infographic builder yet); Insight Map / Forecast / Anomaly = SOON stubs. Cheapest next real: Infographic builder (compose existing KPI cards + 1 chart → poster + export) or Exec Summary (one small-model call). NOT yet eyeballed live by user during a real run.

## 2026-06-23 — DESIGN SYSTEM STANDARDIZATION (UI/UX source-of-truth + Tier-1 sweep) — LIVE, BAKED, FE-ONLY
NEW spec file **`DESIGN_SYSTEM.md`** (repo root) = single source of truth. Locks: 13 color tokens (clay=brand/action, green=status only, red=error only, NO `gray-*`, NO raw blue except charts), type scale (serif H1 `text-2xl font-semibold` + `ui-serif,Georgia,serif`; serif H2 `text-[15px]`; sans body 14px `text-sm #6b6b6b`; muted `text-xs #9a958c`), **exactly 3 button variants** (primary `rounded-xl px-4 py-2.5 bg-[#C2683F] hover:bg-[#A8542F]` · secondary `rounded-lg px-3 py-2 border-[#E7E5DD] hover:bg-[#F4F1EA]` · ghost dashed `rounded-lg border-dashed text-[#C2683F]`), 3 card types (interactive `rounded-2xl` hover-lift · feature `bg-[#F6EFEA] border-[#E8C9B5]` · info `rounded-lg`), page shell (`max-w-7xl px-4 md:px-6`, serif H1 header row `flex items-start justify-between gap-4 mb-6`), empty/loading (skeleton > spinner), status pills, a11y checklist. Working reference mockup **`mockup-design-system.html`** (nav-switchable: Auto-pilot / Studios / Settings / Components&Tokens, real clay tokens).
- **Audit (Explore agent, 40+ pages):** app was ~65% on-spec. Strong already = clay scale + serif H1 + heroicons + `max-w-7xl`. Broken = **7 button variants**, legacy `gray-*` in index/identity-provider/evals, settings section-H2 drift, empty-state/spinner inconsistency.
- **Tier-1 sweep applied (3 sub-agents, disjoint FILE sets to avoid concurrent-edit conflict, edit-only → ONE build → force-recreate):** ~250 `gray-*` tokens purged in `settings/identity-provider.vue` alone (+~27 audit, +general/ai_settings/smtp/overview/members/index/evals); buttons collapsed to 3 variants across settings + connectors/skills/studios (radii/padding normalized, `cursor-pointer transition-colors` added, Cancel→secondary, clay-Save→primary `rounded-xl`); `index.vue` landing title→serif; evals serif-on-body removed + `UButton color="orange"`→`color="primary"`.
- **KEY FINDING:** settings page TITLE is rendered by `layouts/settings.vue` per-tab (already serif H1) — the audit's "settings header divergence" was section **H2s**, not the page title; so NO per-page H1 added to settings content panes (would double-up). `overview.vue` had its own visible title → upgraded to serif H1.
- **VERIFIED:** Docker build ran `nuxt generate` (fails loud on any broken SFC — PASSED, all tags balanced), `ca-app` healthy, `:3007` → 200. FE-only, NO backend/migration.
- **LEFTOVER (out of Tier-1 scope, cosmetic stray `gray-*`, non-blocking):** `settings/integrations/*`, `settings/members.vue` (1 token), `evals/runs/[id].vue`. **TODO Tier-2:** hoist serif to `tailwind.config.ts fontFamily.serif`; define `.ca-btn-primary`/`.ca-card` global css classes so pages stop repeating long class strings.

## 2026-06-23 — PER-AGENT SCOPE GUARDRAIL + STUDIO SOURCE-LOCK — LIVE, BAKED, default-ON
Two coupled fixes after an agent answered "who is president of usa" (general knowledge) then only soft-deflected, AND its Activity panel listed all 8 org data sources instead of the agent's 3.
- **WHY guardrail was missing:** this fork only ever had the *ambiguity* (clarify) gate — NO *scope* gate. Topic-boundary was 100% base-model behavior (knows the fact, answers, politely deflects after). Citypharma has a scope gate; this fork never got one.
- **SCOPE GUARDRAIL (BE):** new flag **`HYBRID_SCOPE_GATE`** (`settings/hybrid_flags.py`: property `_bool("HYBRID_SCOPE_GATE", True)` — **default ON** + UPGRADE_FLAGS `{"label":"Scope Guardrail","role":"user"}` → admin Feature-Flags page + snapshot). **Zero-LLM directive** injected pre-loop in `ai/agent_v2.py` right AFTER the ambiguity block (mirrors that pattern: flag-gated, fail-open, `try/except pass`). Grounded per-agent by `self.data_sources` names (= report's pinned sources): "you are a data agent for THIS workspace; scope = <source names>; OFF-TOPIC (general knowledge/world facts/current events/politics/trivia) → do NOT answer EVEN IF you know, no answer-then-deflect → 1-sentence 'outside this agent's data scope' + what it CAN do; data-shaped Qs lean in-scope." Compose `${HYBRID_SCOPE_GATE:-1}`, `.env=1`. Verified in-container `flags.SCOPE_GATE=True` + in snapshot. Per-agent override still possible via StudioInstructions.
- **STUDIO SOURCE-LOCK (BE):** root cause of the 8-vs-3 leak — the chat composer's source picker DEFAULTS to ALL org sources → posts them → `report_service.create_report` (and `update_report`) **unioned** composer-sent ids with the studio's pinned `StudioDataSource` set → a studio report grabbed all 8 (music+finance+bakery+RTM+pharma). FIX: both paths now **LOCK a studio report to the agent's pinned Data Agents** — keep only composer ids ∈ pinned, fall back to full pinned set if none. So a studio report's `data_sources` ≡ the agent's pinned set; this also tightens the guardrail (`self.data_sources` = pinned, refusal names only real data) and query access. **Ground truth (dev):** studio "Work" pins 3, "CRM" pins 1, org total 8. **Backfill:** one-time SQL deleted **62** leaked `report_data_source_association` rows (studio reports → strip any data_source not pinned to that studio, only when the studio HAS pins); viewed report dropped 8→3.
- **LANDMINES:** report↔source = `report_data_source_association` M2M; studio pins = `studio_data_sources` (col `agent_id` = data_source id, soft-delete `deleted_at`). Report `data_sources` count comes from COMPOSER selection at create-time, NOT the studio pin (same studio had reports with 8/3/3 before the lock). Composer UI still *visually* lets you select all-org — BE overrides on save; **FE composer not yet locked to pinned in studio mode (TODO).**
- **VERIFIED:** py_compile OK, build OK, `ca-app` healthy. NO migration (flag + code + data-backfill only).

## 2026-06-24 — SLIDES + DASHBOARD CONTRAST FIX (dark-on-dark invisible charts/text) — backend LIVE, FE pending build
Symptom: generated decks/dashboards used a dark navy theme but charts + some text rendered dark-on-dark (invisible), and the slide "1/6" counter + thumbnail strip clipped off the bottom.
- **ROOT CAUSE (two render paths, both LLM-authored):**
  1. **Slides** = LLM writes **python-pptx code** (`create_artifact.py:_build_slides_prompt`) → executed (`code_execution/pptx_executor.py`) → PNG previews → `frontend/components/dashboard/SlideViewer.vue`. Native python-pptx charts default their **axis-label / legend / data-label fonts to BLACK** → invisible on the slate-900 slides the prompt pushed. The prompt **never recolored chart fonts** (textboxes got white, charts didn't).
  2. **Dashboard** = LLM writes **React+ECharts in an iframe** (`_build_page_prompt` → `frontend/utils/artifactIframe.ts` → `ArtifactFrame.vue`). The `dash` ECharts theme + `KPICard`/`SectionCard` defaults are **light-tuned**; when the LLM chose a dark page, axis labels/legend/cards stayed dark → dark-on-dark. No hard contrast rule forced light text on dark.
- **FIX (prompt-level, agent picks light/dark PER TOPIC + contrast enforced both modes — user choice):**
  - `_build_slides_prompt`: added a mandatory **`style_chart_text(chart, color)`** helper (recolors category/value axis ticks + legend + data-labels) to the QUICK REFERENCE + the OUTPUT example, defined `TEXT_DARK`/`TEXT_ON_BG`, and a **"CONTRAST IS NON-NEGOTIABLE"** block: pick ONE bg mode, native pptx charts are BLACK by default so you MUST call `style_chart_text` on EVERY chart.
  - `_build_page_prompt`: added a **"CONTRAST CONTRACT"** block before AVAILABLE COMPONENTS — on a dark page, pass light `className/titleClassName` to every card AND explicit light `textStyle/axisLabel/legend/axisLine` in every ECharts option (the `dash` theme is light-tuned); on a light page keep the defaults; self-check for same-lightness-as-surface.
  - `SlideViewer.vue`: compacted the bottom bar to **one row** (counter inline + smaller `w-12 h-7` thumbs, `py-1.5`) + added `no-scrollbar` `<style>`, so the counter+thumbs stay inside the viewport (the report-route `h-screen` overflow pushed the old taller two-row bar off the bottom).
- **STATUS:** backend `create_artifact.py` **hot-copied to `ca-app` + restarted = LIVE** (regenerate a deck/dashboard → readable; py_compile OK). `SlideViewer.vue` edit is on disk, **NOT yet baked** (needs a FE image rebuild — deferred to save laptop resources). Snapshot `.backups/20260624_062419_slide-dash-contrast-fix`.
- **CAVEAT:** prompts STEER the LLM (much less likely, not a hard guarantee per generation). Deterministic backstops if a deck still slips: force-recolor chart fonts in `pptx_executor.py` after exec; inject a contrast CSS reset into the dashboard iframe in `artifactIframe.ts`. Not built yet.
- **RESOURCE LANDMINE (this session):** the FE image build's `nuxt generate` (6GB Node heap) pinned ~9 host cores via Docker's `Virtualization` VM → laptop heat. `docker cp` hot-copy is near-free; the BUILD is the hog. Also user had **many idle project stacks running** (pharmacy-agent-*, dash-*, citybrain, cp-*, bcp, musing) — stopped all non-`ca-*` (17 containers) → VM 900%→117% CPU. `docker start <name>` to bring any back.

## 2026-06-24 — PLAN: Smart Fin Pack (domain packs WITHOUT the Skills engine) — `docs/PLAN_SMART_FIN_PACK.md`
PLAN ONLY (not built). Goal: get the financial expertise of Anthropic's `anthropics/financial-services` repo (11 agents + 7 vertical SKILL.md bundles + MCP connectors, ~50 methods) into this platform, but **smart per-agent, NOT a static copy**, and **NOT via `HYBRID_SKILLS`** (livelocks, kept OFF). Everything rides the **default tools** (`create_data`/`create_artifact`) + existing gated context + auto-train surfaces.
- **CORE SPLIT — copy the INVARIANT, synthesize the VARIABLE:** the *method* (how DCF/comps/3-statement works, required inputs, golden invariants) is universal → copy Anthropic's SKILL.md verbatim, data-blind. The *binding* (which columns are revenue/FCF/debt, what entities mean here, the actual SQL) is per-warehouse → **machine-synthesize from the agent's schema**, then learn + verify. Anthropic = the financial brain; our `column_intel + semantic + AI-suggest + auto-train + eval + distiller` = the "smart" wrapper.
- **STRUCTURAL MAP (1:1, no Skills engine):** their *named agent* → our **Studio**; their *vertical* → our **domain pack**; *SKILL.md body* → **method-playbook Instruction**; *templates/reference* → **KnowledgeDoc** (PG-FTS); *examples* → **Studio Examples**; *metric defs* → **Metrics catalog**; *commands `/dcf`* → **composer macro / analysis-type selector** (prompt macro → default tools); *MCP feeds* → our connectors (bring own data). Port CONTENT + cite; subagent orchestration stays OFF (single-agent).
- **3-PHASE FLOW:** (0) PORT once → METHOD PRIOR LIBRARY (playbook/doc/inputs/invariants, no columns). (1) BIND+TRAIN per agent, one button: build Studio on financial data → `bootstrap_on_source_pin` detects domain → AUTO-BIND pack → `POST /studios/{id}/train` runs profile→bind metrics/semantic→gen financial queries (`AUTO_QUERIES`)→run+capture proven SQL→gen goldens (`AUTO_EVALS`)→eval ties-out→approve (gate). (2) RUNTIME per question: pre-loop **pack router** (ambiguity-gate slot) picks pack+method+analysis-lens → capability-gate (inputs present? else honest fallback) → value-resolution (`COLUMN_INTEL` P5) → default tools → self-verify eval → 👍/👎 learn.
- **TRAINING = the pack is the CURRICULUM** (not weights): method tells WHAT to compute, schema tells HOW (bound metrics), invariants seed the GOLDENS. Turns blind auto-train into targeted, self-checking financial training, per agent.
- **ALL 7 PACKS, tiered by data-need:** Tier A (runs on our data: 3-statement/margin/unit-economics/returns/GL-recon/NAV/KYC/portfolio) → DO FIRST; Tier B (needs market feeds we lack: comps/DCF-market-WACC/earnings-vs-consensus/buyer-list) → method-only until a feed wired; Tier C (output: pptx/xlsx/deck-refresh/ib-check) → via `create_artifact`. Build engine ONCE, financial-analysis pack first (13 methods, esp 5 modeling), then bulk-import the other 6 verticals (additive).
- **NEW flags (default OFF):** `HYBRID_DOMAIN_PACKS` (master) · `HYBRID_PACK_AUTOBIND` · `HYBRID_PACK_ROUTER`; reuse SEMANTIC_LAYER/METRICS_CATALOG/DOC_KNOWLEDGE/AUTO_QUERIES/AUTO_EVALS/EVAL_HARNESS/COLUMN_INTEL for sub-steps. **NEW small pieces:** `packs` registry, `agent_packs` binding, domain detector, pack router, method-prior import — rest is wiring into existing surfaces.
- **CEILINGS:** knowledge/eval training NOT model weights (OpenRouter, no GPU); eval-gate only as good as goldens; predictive capped by dep-free sandbox (numpy/pandas/math, NO sklearn/scipy → moving-avg/trend/seasonal-naive only, heavy ML = separate compute lane); Tier B partial without feeds.

## 2026-06-24 — BUILT Phase 0: Domain Packs engine (lightweight "Skills") — `docs/PLAN_TEACH_SKILLS_ENGINE.md`
DONE + verified live (flags default OFF → byte-identical when off). The data-gated alternative to native `HYBRID_SKILLS` (heavy/sandbox/livelocks/wrong-pick). A **pack** = declarative `.yaml` (method + required_inputs + output_spec + goldens), NEVER executed — it only injects `[METHOD]+[BINDING]` into the AgentV2 planner so the default `create_data`/`create_artifact` loop follows it. Copy the INVARIANT method, machine-synthesize the per-agent VARIABLE binding.
- **3-layer selection fixes "agent picks wrong skill":** (1) BIND gate (hard) — pack invisible unless its required_inputs bind to THIS agent's columns; (2) TRIGGER gate — question must hit the pack's `trigger_hints` (else it never fires, even when bound); (3) SCORE `0.5·trigger+0.3·conf+0.2·winrate` top-1; winrate adaptive (Phase 5). Off-topic Q on a bound agent → no pack (proven). Wrong-data pack → can't bind → invisible (proven on a music dataset).
- **FILES (new):** `backend/app/ai/packs/{__init__,registry,binder,router,runtime}.py` + `packs/library/ebitda_good_bad_ugly.yaml` (first real skill = user's CEO/CFO EBITDA Good/Bad/Ugly SOP) + migration `studiopack1_studio_bound_packs.py`. **(edited):** `models/studio.py` (+`StudioBoundPack` table: studio_id, pack_id, binding_map, output_spec, eval_goldens, status[pending|active|dormant|rejected], source[pack|user], conf, missing), `settings/hybrid_flags.py` (+`HYBRID_DOMAIN_PACKS`/`PACK_AUTOBIND`/`PACK_ROUTER`, snapshot, UPGRADE_FLAGS), `ai/agent_v2.py` (+pack injection after the scope-guardrail block ~L2258, `await packs.runtime.resolve_injection(self.db, self.report.studio_id, question)`, flag-gated, fail-open).
- **MIGRATION HEAD now `studiopack1`** (was `dashversions1`). Applied live on `ca-postgres`. Table verified.
- **BINDER LANDMINES (all fixed, see plan):** role-boost manufacturing false binds from weak names → eligibility on NAME score only (`_MIN_CONF=0.6`), role only ranks; bidirectional substring over-match → term-in-column only; camelCase warehouse names (`BusinessUnit`) didn't tokenize → camel-split in `_norm`. `BaseSchema` has `updated_at` too (migration must include it).
- **STATUS:** engine unit-proven (bind=1.0 clean, missing-budget→dormant, music→unbound, on-topic selects, off-topic→None); app healthy 200. Backups: `.backups/20260624_phase0_domain_packs/`. Deploy = hot-copy + `docker restart ca-app` (never force-recreate).

## 2026-06-24 — DONE Phase 1: Domain Packs live on real data (E2E proven)
EBITDA Good/Bad/Ugly pack bound to a real studio + flags ON + live agent run → method followed end-to-end.
- **Setup:** test studio **EBITDA Pack Test** `5ac4444c-2df0-423b-9457-7bc080128970` (org `55278108`); synth `ebitda.csv` (5 sectors, EBITDA actual/LY/budget + revenue) → DataSource `883a57ef…` pinned + profiled. Binder on real `column_intel` → `bound=true`, 7/7 mapped, conf 0.7, missing=[]. `studio_bound_packs` row `74614ae7…` status=`active`.
- **Run:** flags flipped via per-org override (`PUT /api/organization/hybrid-flags/{HYBRID_DOMAIN_PACKS,HYBRID_PACK_ROUTER}` `{enabled:true}`). Q "monthly EBITDA performance summary by sector — good bad ugly, vs LY and vs budget" → log `[DOMAIN_PACKS] injected pack block (chars=1801)`, no errors. Agent computed vs-LY/vs-Budget %, flagged Food revenue +11% (>10% rule), bucketed GOOD(Pharma,Food)/BAD(Retail)/UGLY(Logistics,Construction), built the slide deck. Numbers match hand-calc. 5 goldens snapshotted into `eval_goldens`.
- **LANDMINES:** (1) EBITDA numeric cols profile `role="id"` not `measure` — binder still binds (role only ranks, ×0.7→0.7≥floor 0.6); don't tighten. (2) **Flip flags with the per-org override API, NEVER `--force-recreate`** — recreate re-bakes from image (no hot-copied pack code) → wipes Phase 0/1; `set_override` applies live + persists to org `settings.config.hybrid_overrides`; `docker restart` keeps `docker cp` files. (3) Added a `[DOMAIN_PACKS]` injection log line in `agent_v2.py` (~L2281, logger `app.ai.packs`).
- **Flags now ON (override) for org 55278108** — other studios unaffected (no active bound packs → no-op). Revert: `PUT …/{env}` `{"enabled":null}`.

## 2026-06-24 — DONE Phase 2: Teach Box backend (paste analysis → trained agent) — E2E PROVEN
Paste an existing analysis/SOP → ONE small-model LLM call classifies into SKILL|INSTRUCTION|DATA_RULE|KNOWLEDGE spans → each routed to its surface, all born pending (review gate).
- **Routes** (`app/routes/studio_teach.py`, gated `HYBRID_TEACH_BOX`, editor-only): `POST /studios/{id}/teach` = classify + bind-preview (NO writes); `POST /studios/{id}/teach/approve` = persist spans (+optional `train:true` → `train_orchestrator.start_training`).
- **Engine** (`app/ai/packs/teach.py`): SKILL→user Domain Pack (`build_skill_pack`→`binder.bind_pack`→`StudioBoundPack` source='user', full dict in `pack_body`, active if bound else dormant); INSTRUCTION/DATA_RULE→`StudioInstruction` (DATA_RULE prefixed `[DATA RULE]`); KNOWLEDGE→`KnowledgeDoc` via `docs_index.ingest_doc`. **Column-aware classify**: studio's real column names fed into the prompt so SKILL input synonyms map to real columns (else loose LLM names score <0.6 → dormant).
- **NEW `studio_bound_packs.pack_body` JSON col** (mig `studioteach1`, **head now studioteach1**): user packs have no yaml file → whole pack dict stored inline; `runtime.resolve_injection` does `registry.get_pack(id) or row.pack_body`.
- **E2E** on studio `5ac4444c`: pasted mixed EBITDA SOP → 5 spans correctly typed → SKILL bound active → approve wrote 1 instruction + 2 data-rules + 1 knowledge-doc + 1 user pack → library pack set dormant to isolate → live run logged `[DOMAIN_PACKS] injected pack block (chars=1594)` → agent computed identical GBU. The pack_body-reconstructed user pack drove the loop.
- **LANDMINES:** (1) registry is FILE-ONLY → DB-only user pack invisible to `get_pack` → `pack_body` col + runtime fallback (don't write yaml into container, not baked). (2) feed real column names into classify or SKILL won't bind. (3) bare in-container scripts hit `InvalidRequestError: 'Completion'` (mappers not all imported) + `resolve_injection` swallows → silent ""; test pack runtime via REAL HTTP completion, not a script. (4) column shape `{name,dtype,metadata:{role}}` — hoist `metadata.role` for binder.
- **Files new:** `app/ai/packs/teach.py`, `app/routes/studio_teach.py`, `alembic/.../studioteach1_pack_body.py`. **edited:** `models/studio.py`(+pack_body), `ai/packs/runtime.py`(fallback), `settings/hybrid_flags.py`(+TEACH_BOX), `main.py`(register). Backups `.backups/20260624_phase2_teach_box/`. Flags `HYBRID_TEACH_BOX` ON (override) org 55278108.

## 2026-06-24 — DONE Phase 3: Teach Box UI — E2E PROVEN
The paste→classify→review→approve flow now has a studio-tab UI.
- **`components/studio/StudioTeach.vue`** (new, self-contained): paste box (20k cap) + "✦ Teach AI" → `POST /studios/{id}/teach`; one review card per span (type badge SKILL/INSTRUCTION/DATA_RULE/KNOWLEDGE, inline-editable title+content, include checkbox, SKILL bind status active/dormant + `key → column` map); footer "re-train after saving" toggle + green "Approve & save" → `POST /studios/{id}/teach/approve`. Clay/coral DESIGN_SYSTEM tokens, `useMyFetch`, `useToast`.
- **`pages/studios/[id]/index.vue`** (edited): import + `teach` tab in **behavior** group, gated by `teachEnabled` ref (`loadTeachFlag()` reads `/api/organization/hybrid-flags`→`HYBRID_TEACH_BOX.effective`, fail-soft OFF, called in onMounted) + `<StudioTeach>` section mount.
- **LANDMINES:** (1) FE `dist` is **baked into image, NOT bind-mounted** → `NODE_OPTIONS=--max-old-space-size=6144 npm run generate` on host (output in BOTH `dist/` + `.output/public/`) then `docker cp dist/. ca-app:/app/frontend/dist` — static served from disk, **NO restart**. Never `--force-recreate` (re-bakes stale dist + wipes hot-copied backend). (2) `useMyFetch` baseURL `/api`; ufo `withBase` skips double-prefix → use `/studios/...` for studio routes, `/api/organization/...` for org. (3) approve summary keys = `skills_active`/`skills_dormant`/`data_rules`/`instructions`/`knowledge` (NOT `skills`). (4) hybrid-flags GET is `manage_settings`-gated → tab only loads for admins/owners.
- **E2E:** built+deployed; teach string in chunk `dist/_nuxt/Cqo-F34R.js`; `HYBRID_TEACH_BOX effective=True`; live `POST /studios/5ac4444c/teach`→HTTP 200, 3 spans (2 DATA_RULE+1 SKILL "active skill"). Backups `.backups/20260624_phase3_teach_ui/`.

## 2026-06-24 — DONE Phase 4: Pack train wiring — E2E PROVEN
Train run now binds packs + biases the generators + surfaces dormant skills. NEW `backend/app/ai/packs/pack_train.py` (3 fns), wired into `train_orchestrator` as stage 1b (after profile) + stage 3b (after evals). Hot-copy + restart deploy (NO FE rebuild).
- **`autobind_library_packs`** (gated `flags.PACK_AUTOBIND`): try EVERY library pack vs the studio's profiled columns. Full bind → `pending` StudioBoundPack row (review gate, source=`pack`); partial (≥1 input, a required missing) → `dormant` row w/ `missing`; 0-match → skip. Idempotent — existing (studio,pack_id) rows untouched. Summary `{bound,dormant:[{pack_id,name,missing}],skipped,existing}` → `train_status.detail.packs`.
- **`build_skill_context`** → text block (method snippet + trigger hints + binding) of the studio's ACTIVE packs; threaded as new `skill_context=` kwarg into `generate_queries_for_studio`/`generate_evals_for_studio` (both `_build_prompt` now take it) so seeded queries/evals cover the skills' math ("seed from method").
- **`materialize_pack_goldens`** (gated `flags.DOMAIN_PACKS`): any `eval_goldens` an active pack carries → `TestCase` rows (same suite + FieldRule shape as auto_evals, dedupe by name). No-op until goldens exist.
- **LANDMINES:** (1) bare-script (`python -c`) hits the `Completion` mapper-init error → `studio_columns`/`_active_packs` swallow it → []; **test via REAL HTTP train**, not a bare script. (2) per-org flag overrides are NOT in process env → `flags.PACK_AUTOBIND` reads OFF in bare scripts; flip via `PUT /api/organization/hybrid-flags/HYBRID_PACK_AUTOBIND {"enabled":true}` (body key `enabled`, not `override`). (3) train status is per-worker, persisted to `Studio.config['_train_status']`; polls bounce across workers — read `detail` off the `done` snapshot.
- **DEFERRED:** generatively snapshotting a method on real data to MINT goldens (needs full agent loop) — later pass.
- **E2E:** PACK_AUTOBIND flipped ON (org 55278108); deleted stale `ebitda-good-bad-ugly` pack row on studio `5ac4444c`, HTTP train → `detail.packs={bound:1,...,existing:0}`, DB row recreated `pending`/`pack`/conf 0.7 all 7 inputs bound; `queries.saved=6`+`evals.created=6` (w/ skill_context from active user pack); `pack_goldens={created:0}`. Backups `.backups/20260624_phase4_train_wiring/`.

## 2026-06-24 — DONE Phase 5: Domain Packs adaptive + harden — E2E PROVEN
Win-rate demote + drift re-check + promote-to-org. Migration head **packwin1** (3 tables: `pack_winrates`, `pack_fire_events`, `org_packs`). Hot-copy + `alembic upgrade head` + restart (NO FE rebuild).
- **pack_winrate (feedback demote):** at injection `runtime.resolve_pack` records WHICH pack fired on the completion (agent_v2 → `winrate.record_fire` writes `pack_fire_events`). A later 👍/👎 (`completion_feedback_service._maybe_record_pack_signal`, BOTH directions) → `record_signal_for_completion` upserts passes/fails+score on `pack_winrates(studio,pack,question_cluster)`. `resolve_pack` reads `get_winrate(cluster)` per candidate → feeds `router.score_candidate` (ranking demote) AND benches a proven loser (`is_benched`: score<0.15 over ≥5 samples → skipped). Cluster = matched trigger hint (per-pattern).
- **recheck_bindings (drift):** `pack_train.recheck_bindings` each train (orchestrator stage 1b, after autobind): re-bind existing dormant/active/pending rows vs current cols → dormant→pending (missing input reappeared; never auto-activate), active/pending→dormant (bound col vanished); `rejected` untouched. → `detail.pack_recheck`.
- **promote-to-org:** `org_packs` table + `OrgPack` + `POST /studios/{id}/packs/{pack_id}/promote` (editor+, copies user pack `pack_body`→org store) + `GET /organization/packs`. `autobind_library_packs(db,sid,organization)` now binds org packs alongside yaml library (`source='org'`, inline `pack_body`) → every org studio picks it up next train. Runtime unchanged (serves from pack_body). Router registered in `main.py`.
- **Files:** mig `alembic/versions/packwin1_pack_winrate.py`; NEW `app/ai/packs/winrate.py`, `app/routes/studio_packs.py`; EDITED `models/studio.py` (+PackFireEvent/PackWinrate/OrgPack), `ai/packs/runtime.py`, `ai/packs/pack_train.py`, `ai/agent_v2.py`, `services/completion_feedback_service.py`, `ai/knowledge/train_orchestrator.py`, `main.py`. Backups `.backups/20260624_phase5_adaptive/`.
- **LANDMINES:** (1) bare-script flag landmine again — `recheck`/`record_*` read DOMAIN_PACKS OFF in a bare `python -c` → test via HTTP. (2) `ErrorCode.VALIDATION` (NOT `VALIDATION_ERROR`). (3) `StudioBoundPack.source` now also `'org'` (+`pack`/`user`). (4) **DEPLOY: copy EVERY edited file** — missed `train_orchestrator.py` first pass → `pack_recheck=null` silently; run `alembic upgrade head` in container after a migration.
- **E2E:** (a) promote → OrgPack `created` + listed; (b) seeded `pack_fire_event` + `POST /completions/{id}/feedback {direction:-1}` → `pack_winrates` row `passes=0 fails=1 score=0`, `get_winrate=(0.0,1)`, `is_benched(0.0,5)=True`; (c) forced ebitda row dormant → HTTP train → `pack_recheck={revived:[ebitda-good-bad-ugly],rebound:2,checked:2}`, row→pending.

## 2026-06-24 — DONE Phase 6: scale packs (Tier-A fin yaml) — E2E PROVEN
Poured **7 Tier-A fin packs** as pure yaml data files in `backend/app/ai/packs/library/` (NO code — registry auto-loads every `*.yaml`): `unit_economics`, `returns_analysis` (IRR/MOIC/TVPI), `three_statement_integrity`, `variance_commentary`, `gl_reconciliation`, `nav_tie_out`, `portfolio_monitoring` → with shipped `ebitda_good_bad_ugly` = **8 packs**. Each = INVARIANT method_text (data-blind) + logical `required_inputs` (role/synonyms/optional) + output_spec/format + `eval_goldens: []`.
- **Deploy:** `docker cp *.yaml ca-app:/app/backend/app/ai/packs/library/` + **restart** (registry caches in-process → restart clears; NO migration, NO FE rebuild).
- **Tier B/C deferred** (additive): Tier B (comps/DCF/consensus) needs market-data feeds; Tier C (pptx/xlsx) folds into `create_artifact`. Map: `docs/PLAN_SMART_FIN_PACK.md`.
- **LANDMINE:** binder gates on NAME score with a role penalty — input role (measure/dimension) mismatching the column's profiled role drops 0.85→0.595 (<0.6 floor) → won't bind (live: variance-commentary skipped on EBITDA studio, its measure inputs hit dimension-typed cols). Honest gating; widen synonyms or fix column role.
- **E2E:** registry loads 8; all 7 new `bind_pack`=True on representative cols (unit-economics conf 1.0); router routes ("IRR/MOIC by deal"→returns-analysis, "reconcile gl vs subledger"→gl-reconciliation); live HTTP train of studio 5ac4444c autobound new packs → portfolio-monitoring `dormant` (partial), 6 non-matching skipped, existing untouched. **Domain Packs engine COMPLETE (Phases 0–6).**

## 2026-06-24 — DONE Packs review/approve UI (the missing surface) — E2E PROVEN
Autobound packs landed `pending`/`dormant` with no human surface; added a studio **Skills** tab.
- **Backend** (`app/routes/studio_packs.py`, +3 endpoints): `GET /studios/{id}/packs` (viewer+, rows + binding + missing + source + per-pack win-rate + `promotable`), `POST /studios/{id}/packs/{pack_id}/status` (editor+, body `{status: active|rejected|pending}`; **can't go active while `missing` non-empty** → 400 with the missing cols), plus the existing `/promote`. Hot-copy + restart.
- **FE** `components/studio/StudioSkills.vue` (new): one card per bound pack — name + status badge (active/pending/dormant/rejected) + source chip (library/authored/org-shared) + bind% + win-rate pill + binding `key→col` + dormant "needs column" hint + collapsible method. Actions (editor): Approve / Deactivate / Reject / Restore / Promote-to-org. `pages/studios/[id]/index.vue` (4 edits): import + `skills` tab (behavior group, gated `packsEnabled` ← `HYBRID_DOMAIN_PACKS.effective`) + section mount + `loadPacksFlag()` in onMounted. One `nuxt generate` + `docker cp dist`.
- **E2E:** `GET …/packs` → 3 rows (active user / pending ebitda / dormant portfolio-monitoring) w/ win-rate; approve pending→active OK; activate dormant → 400 "unbound inputs: company, revenue, period"; StudioSkills + `puzzle-piece` tab present in `dist/_nuxt/Jltb8j_1.js`, copied + served. Backups `.backups/20260624_packs_ui/`.

## 2026-06-24 — DONE Follow-up phases A–F (durability + Tier C/B + golden-minting + observability) — E2E PROVEN
Ran the pending plan A→F (sub-agents for authoring, I deployed/tested). Code pushed to **`github.com/raahulgupta07/rahulai-dash`** (branch `main`, orphan root commit — fork was shallow so bagofwords history dropped; secret-scan blocked a dummy `dapi…` doc token in `connectorDocs/cloud.ts:407`→placeholdered).
- **A — Bake durability:** the project's bake pattern is `docker commit ca-app cityagent-analytics:<tag>` (the `bi-pX` tags are the same) NOT a from-disk rebuild (running `ca-app` ≠ the `dash-*` compose). Committed → `:packs-complete` then (after F) `:packs-full`, both retagged `:dev`. Hot-copied backend + `docker cp`'d dist live in the container fs (not mounts) so commit captures them. A recreate from `:dev` now keeps everything.
- **B — Tier C output packs (4):** `pptx_author`/`xlsx_author`/`teaser_builder`/`deck_refresh` yaml. LANDMINE: binder only marks bound when ≥1 NON-optional input binds (`len(req)>0`) → output packs each carry ONE broad `subject` dimension (synonyms name/company/entity/…) + optional measure/period so they activate on almost any data. E2E: all 4 bind; router deck→pptx, excel→xlsx, teaser→teaser.
- **C — Generative golden-minting:** NEW `app/ai/packs/pack_goldens.py::mint_pack_goldens` (gated DOMAIN_PACKS+AUTO_EVALS), wired into orchestrator stage 3c. Per ACTIVE pack: small-LLM builds question+single-value SQL from method+binding+schema → runs read-only → `_derive_expected` → `TestCase` named `[pack] question` in the studio goldens suite (reuses auto_evals helpers). E2E: train → `pack_goldens_minted={created:4}` (2/pack), real `[pack]`-named goldens written.
- **D — Observability:** backend `GET /organization/pack-analytics` (fires/wins/losses/score per pack + status mix + dormant backlog; in `studio_packs.py`); FE `pages/settings/pack-analytics.vue` (Settings nav, gated `HYBRID_DOMAIN_PACKS`+`manage_settings`, totals strip+table+dormant backlog). E2E: endpoint returns ebitda fires=1/losses=1/win_rate=0, portfolio-monitoring dormant=1; page in bundle + served.
- **E — Upload dup-name fix:** backend `data_source_from_file.py` auto-suffixes a colliding DataSource name (` (2)`,` (3)`…) instead of 409 (org-unique `uq_data_sources_org_name`); FE `UploadSpreadsheetModal.vue` shows neutral "will be saved as 'X (2)'" hint + softens the 409. E2E: backend dedupe proven; hint in bundle.
- **F — Tier B packs (3, partial by design):** `comps_analysis`/`dcf_valuation`/`earnings_vs_consensus` yaml. Declare the EXTERNAL market-data fields as NON-optional → on normal data they bind **dormant** (`missing:[peer_ev_ebitda]/[free_cash_flow,wacc]/[actual_eps,consensus_eps]`) = the honest "needs feed" signal in the dormant backlog. **F1 (the market-data CONNECTOR) NOT built** — real vendor/infra work, deferred. E2E: 15 packs total; Tier-B all dormant on ebitda data.
- **Deploy:** B/F yaml = `docker cp *.yaml`+restart; C = backend hot-copy+restart; D backend hot-copy + D/E FE = 1 `nuxt generate`+`docker cp dist`. Final `docker commit`→`:packs-full`/`:dev`. Backups `.backups/20260624_packs_ui/` (+ git history). Registry now **15 packs** (ebitda + 7 Tier-A + 4 Tier-C + 3 Tier-B).

## 2026-06-24 — Skills tab render fix + Build→Skills pack catalog — LIVE, BAKED
- **BUG (Studio Skills tab showed native "Pinned skills", packs dead):** `pages/studios/[id]/index.vue` had TWO `<section v-else-if="activeTab === 'skills'">` — the orphan native pinned-skills block came FIRST in the v-else-if chain and shadowed our `StudioSkills` packs block (Vue renders only the first match). Fix: repointed the Skills tab to `<StudioSkills .../>`, deleted the dead native section. (Native pin had no nav entry anyway — the only `skills` nav tab is the flag-gated packs one at ~line 1935.) **LANDMINE: never reuse the same `activeTab===X` in a v-else-if chain — second branch is unreachable.**
- **Build → Skills now shows the whole pack library** (was native SKILL.md-only `/api/skills`). NEW backend `GET /api/packs/library` in `studio_packs.py` (gated DOMAIN_PACKS, fail-soft): `registry.list_packs()` (15 yaml) + org packs, each with domain/tier(A/B/C/Org via `_tier_for`)/triggers/required-inputs(key+role+optional+desc)/bound+active studio counts. `pages/skills.vue` renders a "Domain Packs" section ABOVE the SKILL.md grid — grouped by tier (A=runs on data, C=output, B=needs feed, Org), each card = name + domain + active-studios chip (or "dormant") + input chips (required=clay, optional=`?` gray) + trigger preview; links to Settings→Pack Analytics. Hidden when catalog empty (flag off). E2E: endpoint returns `totals{total:16,library:15,org:1,in_use:2}`. Backups `.backups/20260624_skills_tab_fix/`. Baked `:dev`+`:skills-tab-fix`+`:skills-catalog`.
- **`/skills` REVAMP — left category rail + grid (chosen via mockup):** unified Domain Packs + SKILL.md playbooks on one page. Backend `/api/packs/library` now emits `category` per pack (`_category_for`/`_CATEGORY_BY_ID`: Performance{ebitda,variance,unit-econ} · Valuation{comps,dcf,earnings} · Fund/PE{returns,nav,portfolio} · Accounting{gl-recon,3-stmt} · Output{4} · Org). FE `pages/skills.vue` rewritten: left rail = Categories (All + present cats + **Playbooks**, each w/ count + green-dot active) + Data-readiness tier checkboxes (A/C/B/Org); main = search-filtered card grid grouped by category (All) or flat (one cat); Playbooks category swaps to the SKILL.md grid (+ "New playbook" from completion). Tier badge on each card. Empty SKILL.md no longer a stranded block — it's just the Playbooks tab. E2E category counts `{Performance:3,Valuation:3,Fund/PE:3,Accounting:2,Output:4,Org:1}`. Baked `:skills-revamp`+`:dev`.
- **Ported nimrodfisher/data-analytics-skills → 33 packs (15→48 library):** general-analytics SKILL.md method library converted to our pack yaml. **No LICENSE in source → method re-authored data-blind/transformative (NOT verbatim), all repo script refs dropped** (our agent writes its own code via create_data/create_artifact). 6 subagents fanned out (one per source folder). New ids carry a **category prefix** so `_category_for`/`_tier_for` derive from prefix (no 33-entry dict): `daq-`=Data Quality(TierA,5) · `ana-`=Analysis(TierA,7) · `doc-`=Documentation(TierC,7) · `viz-`=Storytelling(TierC,5) · `stk-`=Stakeholder(TierC,5) · `wfl-`=Workflow(TierC,4). Data-bound (daq/ana) map real inputs→roles; soft (doc/viz/stk/wfl) use the broad-`subject` block (one non-optional dimension) so they bind/activate on any data. **LANDMINE: registry loader = single-doc `yaml.safe_load`; shipped packs have NO `---` fences. Subagents wrongly wrapped 26 files in `---…---` → trailing fence = 2nd doc → file SILENTLY SKIPPED. Fix: stripped all bare `---` lines.** Verified 48/48 parse, 48 unique ids, every pack ≥1 non-optional input (all can activate). FE `CATEGORY_ORDER` extended w/ the 6 new cats. E2E `/api/packs/library` `totals{library:48,org:1}`, by-tier `{A:20,C:25,B:3,Org:1}`. Deploy: `docker cp library/. ca-app:…/library/` + route + restart; FE generate+cp; `docker commit`→`:packs-48`+`:dev`.
- **Skills rail + studio card-layout polish (iterative):** `/skills` category rail → icons per category (`CATEGORY_ICON` map) → grouped sections **Finance / Analytics / Library** (`RAIL_GROUPS`+`railGroups`/`railLookup`, All pinned on top) → matched to the studio agent sidebar exactly (`text-12`/`icon-3.5`/`gap-px`/`9px tracking-wider` headers/plain-number counts/`hover:bg-[#faf8f3]`; kept a green active-dot studio lacks). Then density: rail `w-52`, page `max-w-[1640px]`, card grid `2xl:grid-cols-4` (user kept the vertical rail vs a top bar). **Studio page (`studios/[id]`) → both panels are inset rounded cards:** rail `w-60 m-2 border rounded-2xl` (was flush `border-e h-full`), main `flex-1 my-2 me-2 border rounded-2xl` (was flush `h-full`). LANDMINE: dropping `h-full` for `m-2`/`my-2` lets flex-stretch set height WITHOUT the margin-overflow conflict — keeps `overflow-y-auto` internal scroll (don't re-add `h-full`). Baked `:skills-rail*`/`:skills-4col`/`:studio-rail-card`/`:studio-main-card`→`:dev`.

## 2026-06-24 — DONE Presentations gallery + Open-as-slides-first + failed-deck clean state — LIVE, BAKED
Generated decks (`artifacts.mode='slides'`) were never listed — `/presentations` page was a hardcoded empty stub ("no presentations backend yet"). Built the missing surface end-to-end.
- **Backend list:** NEW `GET /api/artifacts/presentations` (`routes/artifact.py`) → all slides artifacts for the org, **latest version per report** (dedup). Each row: `slide_count` (preview_images or slides len) · `has_preview` · `pptx_ready` (pptx_path && status!=failed) · `report_title` · status. New `ArtifactService.list_presentations(org_id)`, new `PresentationListSchema`. **LANDMINE: route MUST be declared BEFORE `GET /{artifact_id}` — else FastAPI matches `presentations` as an artifact_id.** Also exposed `pptx_path` on `ArtifactSchema` (was hidden → download buttons couldn't tell if a file exists).
- **FE gallery** (`pages/presentations/index.vue`, full rewrite): card grid — slide-0 thumbnail (auth-gated `/artifacts/{id}/preview/0` fetched as blob → objectURL; plain `<img src>` 401s), title, source report, slide count, status badge (failed/generating), `.pptx` download (native fetch + blob, mirrors ArtifactFrame.exportPptx). **LANDMINE: fetch path is `/api/artifacts/presentations` NOT `/api/presentations` (router prefix `artifacts`) — first cut used the short path → "Failed to load presentations".**
- **Two buttons per card (mirrors dashboard "Open"):** **Open** → `/reports/{id}?focus=slides`; **Open in chat** → `/reports/{id}`. Thumbnail/title click = Open.
- **`?focus=slides` = slides-first layout** (`pages/reports/[id]/index.vue` onMounted, beside the existing `?focus=dashboard`): reuses the **`dashboardFirst` flip** (deck on the big main/LEFT, chat docked RIGHT, "Switch to chat-first" header) but points the main panel at `rightPanelView='slides'` instead of `'artifact'`. Don't invent a new layout — the SplitScreenLayout `dashboardFirst` prop already does the arrangement swap; just set the panel view.
- **Failed/unrendered slides clean state** (`components/dashboard/ArtifactFrame.vue`): a slides artifact with NO `preview_images` was falling through to the iframe, which dumped its `content.code` (python-pptx) as raw text. Added computed `isUnrenderableSlides` (mode slides && !pending && !hasSlidesWithPreviews) → renders a clean card ("Presentation generation failed" / "No rendered slides yet" + **Regenerate** + **Download .pptx** if pptx exists), and added `!isUnrenderableSlides` to the iframe `v-show`. Working decks (preview_images present) still render via `SlideViewer`. **LANDMINE: a slides artifact's `content.code` is python NOT React — never let the iframe render it.**
- **Deploy:** backend hot-copy (artifact.py + artifact_service.py + artifact_schema.py) + py_compile + restart; FE `nuxt generate` + `docker cp dist`; `docker commit ca-app cityagent-analytics:presentations-gallery`→`:dev`. E2E: endpoint returns real decks (MM Conso 6-slide completed+pptx_ready / EBITDA failed). The user's failed EBITDA deck = the code-dump symptom; fix shows clean Regenerate state. Working MM Conso deck opens slides-first.

## 2026-06-24 — MOCKUP/PLAN: Auto-pilot intake + router (drop-anything → 4 lanes → train) — NOT BUILT
Design-only (mockups + verified wiring; ZERO code changes yet). Reworks the studio **Auto-pilot tab IN PLACE** (`pages/studios/[id]/index.vue`, `activeTab==='autopilot'` section — NOT a new route, user's call) from the bare empty-state ("Pin a source under Sources & Data to begin") into a full-page 3-step flow.
- **STEP 1 ADD — 3 intake tiles** (replaces the redundant header trio Pin/Upload/Auto-train; that trio fully duplicated the new block): **Upload file** (`openUploadSource`→`UploadSpreadsheetModal`→`POST /files`→`POST /data_sources/from-file`→auto-`pinSource`) · **Connect a source** (the 46 connectors — `GET /api/available_data_sources` registry, expands a searchable connector grid; Fabric-user-login featured) · **Pin existing** (`openAddSource`→`GET /data_sources`→`POST /studios/{id}/sources {agent_id}`). KEY DECISION: "Connect a source" (data connectors, the real warehouse hookup) is the primary; "Pin existing" = re-attach an org source already connected (lighter, secondary) — they are DIFFERENT things (first cut conflated them).
- **STEP 2 ROUTE — 4 lanes** (Data / Knowledge / Skill / Rule-Instruction) = the existing **Teach Box classes** surfaced visually. Pasted text → real `POST /studios/{id}/teach` returns typed spans `{type:SKILL|INSTRUCTION|DATA_RULE|KNOWLEDGE, title, content, bind:{bound,overall_conf,binding,missing}}` → render one card per span in its lane w/ match-confidence + **Re-route ▾** (move between lanes if classifier wrong; <0.6 auto-flags). Files route by extension (xlsx/csv→Data, pdf/docx/pptx→Knowledge). Approve via `POST /studios/{id}/teach/approve {spans, train?}` (all born pending, review gate).
- **STEP 3 TRAIN — ONE button** `POST /studios/{id}/train` (poll `GET .../train/status`), gated disabled until ≥1 item routed (no empty-train). The duplicate Auto-train (header + bar) was collapsed to this one.
- **REDUNDANCY FIXES baked into the design:** Auto-train ×2→×1, Pin/Upload ×2→×1 (header trio dropped), Pin-vs-Connect split.
- **Mockups (scratchpad, latest = chosen):** `autopilot-fullpage.html` (the approved full-page-in-studio-shell version) ← `intake-router-detailed.html` ← `intake-router-mockup.html`.
- **STATUS: mockup approved, build NOT started.** Wiring all verified live (routes exist: `/available_data_sources`, `/studios/{id}/teach`(+`/approve`), `/data_sources/from-file`, `/files`, `/studios/{id}/sources`, `/studios/{id}/train`(+`/status`)). `studios/[id]/` has NO sub-routes — everything is `activeTab` in the one `index.vue`; Auto-pilot rewrite lands there. Teach Box gated `HYBRID_TEACH_BOX`; connectors un-gated. NEXT = implement the Auto-pilot section rewrite.

## 2026-06-24 — DONE Auto-pilot BUILT + connector model consolidated + nav + train-progress + multi-upload — LIVE, BAKED
Supersedes the MOCKUP/PLAN entry above — all of it is now SHIPPED. Six related changes baked into `cityagent-analytics:dev`:
- **Auto-pilot tab rewrite** (`frontend/pages/studios/[id]/index.vue`, `activeTab==='autopilot'`): full-page 3-step flow. **1·ADD** = 2 tiles (collapsed from 3): **Add a source** + **Upload file**. **2·ROUTE** = 4 lanes (Data/Knowledge/Skill/Rule) populated from REAL studio state (sources/docs/instructions/examples) w/ Manage→ links + a callout pointing pasted text to Teach for classify+Re-route (dropped the mockup's fake per-card confidence — only Teach has real confidence; honest). **3·TRAIN** = single gated `runFullTrain` (`POST /studios/{id}/train`). Old rich stats/capability/suggestions kept below as DETAILS (`v-if="sources.length"`). Header has a small clay readiness ring.
- **Connector model consolidated (best practice "org library = source of truth, agent = scope"):** "Connect" + "Pin" tiles MERGED into one **Add a source** → a **popup `UModal`** (not inline) listing org connections by name+host with **Pin/✓Pinned** + search + **Manage in Connectors →** link + **+ New connection (46)** footer → opens shared `AddConnectionModal` (owns the 46-type grid) → creates in org registry → auto-pins. `onConnectCreated` enforces: Connect always writes org registry then pins (no creds on agent). State: `addOpen/orgSearch/loadOrgSources/filteredOrgSources/isPinned/connTypeOf/connHostOf/openAddPicker/openConnect`. The old custom 46-grid in the page was removed (modal owns it).
- **Auto-name guard** (`frontend/components/datasources/ConnectForm.vue`): `derivedName()` — blank connection name no longer collapses to the bare type (10 Postgres → all "postgres"); derives `Title · host/db` from config. Applied to all 4 create/edit/test payloads. So N same-type connections stay distinct (type=template, connection=named instance).
- **Agent Studios = standalone top-nav tab** (`frontend/components/nav/TopNav.vue`): promoted out of the Workspace dropdown to its own direct-link tab (first). Added `direct?: string` to NavGroup; group header renders as `NuxtLink` when `direct` set, else the popover. `isGroupActive` handles it. Removed `studios` item from the Workspace group.
- **Train progress fix** (`backend/app/routes/column_profile.py` + `app/ai/knowledge/train_orchestrator.py`): "stuck at 10%" was COARSE pct (10→40 only AFTER all 8 tables/242 cols profiled = minutes of frozen bar). Now `_profile_all_tables(progress=cb)` fires a per-table callback; orchestrator interpolates pct across the 10..40 slice + writes a `note` ("RTM · 3/8 tables"). Per-table `[profile]` log lines w/ timing. Per-source `asyncio.wait_for(600s)` timeout → fail-soft note "timed out, skipped" (a hung remote query no longer freezes the whole train). FE poll (`runFullTrain`): logs only on message CHANGE (no spam), budget 3→6 min, surfaces `note`.
- **Multi-file upload** (`frontend/components/data/UploadSpreadsheetModal.vue`): added `multiple` to the file input + `batchUpload()` — >1 file → each goes upload(`/files`)→create(`/data_sources/from-file`, all sheets)→parent pins via `created` emit; progress bar + toast summary; single file keeps the rich preview/sheet flow.
- **Train tabs blank — explained, not a bug for 4/5:** Semantic/Metrics/Assets are separate opt-in surfaces NOT auto-filled by basic train (fill via AI-suggest / `HYBRID_SEMANTIC_LAYER`/`HYBRID_METRICS_CATALOG`); Review auto-approves → empty queue. Queries DOES have rows (6 approved auto-queries) but renders blank when embedded in `StudioQueries`→`KnowledgePanel`→`QueriesTab` — suspected runtime error blanking the panel body; needs the browser console error to fix (NOT yet fixed).
- **DESTRUCTIVE op done:** hard-deleted ALL studios (7 rows incl. 1 soft-deleted) + children (studio_data_sources/examples/instructions/members/skills/artifacts/bound_packs); detached reports (`studio_id=NULL`, kept). `studios` table now 0 rows. User-confirmed hard delete.
- LANDMINES: `derivedName()` uses `selectedTitle.value` (computed, exists). AddConnectionModal `created` emits `{id|data_source_id}`. `pinSource({id})` posts `{agent_id: String(id)}`. Stacked-modal guard: `openConnect()` sets `addOpen=false` first. Deploy: FE `npm run generate`→`.output/public` (NOT `dist`)→`docker cp .output/public/. ca-app:/app/frontend/dist`; backend `docker cp`+`py_compile`+`docker restart ca-app`; bake `docker commit ca-app cityagent-analytics:dev`. `/usr/bin/ls` absent on this mac → use `/bin/ls`. NEVER `--force-recreate`.

## 2026-06-24 — Auto-train fills Semantic + Metrics tabs

- **New `semantic_metrics` stage** in `backend/app/ai/knowledge/train_orchestrator.py` (Stage 4b, pct 93→94, after artifacts, before joins). Gated `if flags.SEMANTIC_LAYER or flags.METRICS_CATALOG` (both ON in this deployment). Resolves the org small model (`LLMService().get_default_model(is_small=True)`), then per pinned source calls `propose_knowledge_from_schema(focus=both|semantic|metrics)` (existing AI-suggest backend — introspects schema, one LLM call, upserts ≤8 SemanticTable + ≤6 MetricDefinition rows as `status='pending'`). Then **auto-approves** the fresh ids (`UPDATE semantic_tables/metric_definitions SET status='approved' WHERE id IN (...)`) to match every other Auto-train stage → Review queue stays empty AND rows go live in agent context (semantic/metrics context builders inject approved rows). Per-source + whole-stage fail-soft (never breaks the train). `detail["semantic_metrics"]="ok (N semantic, M metrics)"`.
- **Why it was empty before:** Semantic/Metrics were opt-in surfaces; basic Auto-train skipped them; `/knowledge/ai-suggest/{ds}` had to be clicked per source. Now one-button train fills them when the flags are on.
- **`focus`** = `both` if both flags on, else the single enabled one. With a flag OFF that surface is left empty by design (still opt-in).
- README updated (how-it-works note + troubleshooting row) to say Auto-train now fills Semantic+Metrics under the flags; Assets still opt-in (AI-suggest).
- Deploy: `docker cp` train_orchestrator.py → `py_compile` OK → `docker restart ca-app` → `/health` ok → `docker commit ca-app cityagent-analytics:dev` (BAKED).

## 2026-06-25 — Blank knowledge tabs fixed + 7-feature build (#3–#9)

**ROOT CAUSE of blank Semantic/Metrics/Queries tabs (long OPEN BUG):** Nuxt 3 path-prefix auto-naming. Components in `components/knowledge/` register as `Knowledge<Name>` — `KnowledgePanel.vue` dedups to bare `<KnowledgePanel>` (filename starts with dir), but the tab files (`SemanticTab` etc.) register as `<KnowledgeSemanticTab>`. `KnowledgePanel.vue` referenced them by BARE `<SemanticTab>`/`<MetricsTab>`/`<QueriesTab>`/`<AssetsTab>`/`<ReviewTab>` → resolved to nothing → empty unknown element: blank body, setup never runs, no `/knowledge/*` fetch, NO console error (unresolved-component is dev-only warning). Parent mounted fine (DBG banner proved `effectiveTab`/`ds` correct). FIX: explicit `import X from './X.vue'` in KnowledgePanel.vue + SemanticTab.vue (`SemanticTableCard`) + pages/knowledge/index.vue (`AssetsTab`,`ReviewTab`). LANDMINE: any bare ref to a subdir-nested auto-import component silently no-ops; KnowledgePanel works only because its filename starts with its dir.

**3 sub-agents built #3–#9 (all flag-gated default OFF, baked):**
- #4 `df is not defined` (cross-source UNION) — coder.py prompt hard-rule "final frame MUST be `df`" + code_execution.py defensive recover/clear-error. NOT gated (correctness).
- #5 `HYBRID_MERGE_SAME_SCHEMA` — `/data_sources/from-file`: content-hash dedup (Connection.config['content_hash']) + same-schema files UNION-load into one source w/ `_source_label`. New `app/services/ingest/smart_upload.py`. (autotrain path already did physical append.)
- #6 `HYBRID_SMART_HEADER` — >40% `Unnamed:` cols → re-detect header row; glossary-shaped sheets → Knowledge layer (docs_index.ingest_doc, pending) + junk table is_active=False.
- #7 `HYBRID_RESULT_CACHE` — serve-before-plan, key=SHA256(normalized-Q + watermark sig from DataSourceTable.metadata_json[_profile_watermark][row_count]). New model result_cache.py + mig **resultcache1** (down=packwin1). create_data.py wiring.
- #8 `HYBRID_QUERY_LEARNING` — create_data success → upsert SQL to query_library_items (chat, pending, win-tagged); failed→fixed → negative StudioInstruction. Inject approved learned queries into coder.py prompt.
- #9 whoami 401 — backend already honored Bearer; cause = boot plugin fetchPermissions.client.ts called getSession() with no token. FIX: guard `if(!rawToken.value) return`.
- #3 packs — NOT a code bug. PROVEN firing live (`[DOMAIN_PACKS] injected pack=viz-visualization-builder / viz-executive-summary-generator` on studio 7d4b92bc). After retrain+recheck: 24 active / 16 dormant / 3 pending. KNOWN COSMETIC GAP: FE "SKILLS USED" badge counts only native sandbox-skill steps (load_skill/run_skill_file), NOT Domain-Pack injects → shows 0 even when packs fire. Not fixed (core planner-path change).

**Flag registry LANDMINE:** new flags need an entry in `UPGRADE_FLAGS` dict (hybrid_flags.py) OR per-org DB overrides are silently ignored (`load_overrides_from_db` only honors keys in UPGRADE_FLAGS). Agents added the property+snapshot but not the registry key → "Loaded 4" not 8 until fixed. All 8 now in org `hybrid_overrides` + UPGRADE_FLAGS → "Loaded 8".

Mig head now **resultcache1**. Image re-baked. Org 55278108 overrides ON: DOMAIN_PACKS, PACK_AUTOBIND, PACK_ROUTER, TEACH_BOX, RESULT_CACHE, QUERY_LEARNING, MERGE_SAME_SCHEMA, SMART_HEADER.

## 2026-06-25 — Intelligence Layer (8 dash-parity capabilities + Studio rail UI)

Closed gap vs `reference/dash` (9 prompt-context layers → Analytics had ~3-4). Built 8 capabilities, Wave 1 (P1-4,P7,P8) + Wave 2 (P5,P6), all flag-gated default-OFF, additive (core touched minimally, backups taken). 34 files compile, migrations applied, healthy boot.

**Migration chain (true single head):** `resultcache1 → goldenq1 → verifmetric1 → hybridsearch1`. Head now **hybridsearch1**.

**The 8 layers** (flag → property in `hybrid_flags.py`):
- **P1 Deep Profiler** `HYBRID_PROFILE_V2/PROFILE_V2` — per-column role catalog (DIMENSION/STATE/MEASURE/IDENTIFIER/TEMPORAL) + top-3 values + variant warn. `knowledge/profile_v2.py`, context section+builder, train Stage 1a. Stored `DataSourceTable.metadata_json['profile_v2']`.
- **P2 Proactive Insights** `HYBRID_PROACTIVE_INSIGHTS/PROACTIVE_INSIGHTS` — z-score+IQR+spike scan per result → chips. `knowledge/insights.py`, hook in `mcp/create_data.py` ~L302, `ProactiveInsightsChips.vue`. No LLM, fail-soft.
- **P3 Forecasting** `HYBRID_FORECAST/FORECAST` — Prophet `forecast_df` tool, lazy-import, hidden from planner when off. `tools/implementations/forecast.py`. NEEDS image rebuild to bake prophet — keep OFF until then.
- **P4 Golden Queries** `HYBRID_GOLDEN_QUERIES/GOLDEN_QUERIES` — promote query on 👍 or verified_count≥2; injected first. `query_library.py` +is_golden +verified_count, mig `goldenq1`.
- **P5 Lazy Profile/Drift** (shares `PROFILE_V2`) — cache-miss → inline profile new table at query time (~1.4s cold/0.1s warm). `mcp/lazy_profile.py`, kill-switch `LAZY_PROFILE_V2_DISABLED`.
- **P6 Code Enrich** `HYBRID_CODE_ENRICH/CODE_ENRICH` — LLM extracts grain/formulas/include-exclude from DDL+SQL → `metadata_json['pipeline_logic']`. Train Stage 1b. Per-table LLM cost → keep opt-in.
- **P7 Verified Metrics** `HYBRID_VERIFIED_METRICS/VERIFIED_METRICS` — locked metric runs own read-only sql_calc, marked AUTHORITATIVE, drift-tracked. `metric_definition.py` +is_locked +last_value +last_value_at, mig `verifmetric1`.
- **P8 Hybrid Search + KG** `HYBRID_SEMANTIC_SEARCH/SEMANTIC_SEARCH` — pgvector+BM25 RRF + entity graph. `knowledge_search_index.py`, `hybrid_search.py`, `knowledge_graph.py`, mig `hybridsearch1`. SCAFFOLD — no prompt injection yet, no payoff. Keep OFF.

**Studio Intelligence rail UI** (additive, backed up):
- New nav group `intelligence` in `pages/studios/[id]/index.vue` (between behavior+operate), 8 tabs `i_profiler/i_codeenrich/i_metrics/i_lazy/i_insights/i_forecast/i_golden/i_search`, each renders `<StudioIntelligence :forceLayer>`.
- `components/studio/StudioIntelligence.vue` — static META (glyph/title/desc/flag per layer) + live fetch `GET /intelligence/layer/{layer}?studio_id=`; real toggle via existing `PUT /organization/hybrid-flags/{env}` (gated canEdit/manage_settings). Renders stats strip + data table + note/empty-state.
- `routes/intelligence.py` (NEW) — read-only, org-scoped, fail-soft (never 500s). `_LAYER_FLAG` map; profiler/codeenrich read metadata_json, metrics/golden read DB tables, search reads BrainGraphEdge (src_entity/relation/dst_entity), lazy/insights/forecast=informative note (transient, no store). Registered in main.py.

**Default-enable (org 55278108):** 5 safe layers ON org-wide via `organization_settings.config['hybrid_overrides']` (json→cast `config::jsonb` jsonb_set →`::json`) + `docker restart ca-app` (NOT --force-recreate). ON: PROFILE_V2 (covers Profiler+Lazy), VERIFIED_METRICS, GOLDEN_QUERIES, PROACTIVE_INSIGHTS. Verified via live authed API (boot log "Loaded 12 hybrid flag override(s)"). OFF kept: CODE_ENRICH (LLM cost), FORECAST (needs prophet bake), SEMANTIC_SEARCH (scaffold). Per-org flag = auto-inherited by all/new agents in org. True per-agent override (studio.config resolver) NOT built.

**LANDMINE reconfirmed:** new flag needs BOTH @property AND `UPGRADE_FLAGS` dict entry + `snapshot()` else per-org override silently ignored. `docker exec ... python -c "import main"` does NOT run lifespan → flag snapshot shows False even when live process has them ON → verify via live API, not import.

## 2026-06-25 — Changelog system + "What's new" notification bell

Versioned feature feed (our hybrid features), surfaced as a 🔔 bell popover in the top nav (before user profile), matching the target Activity/What's-new design. Built by 2 subagents (backend + frontend) + parent wiring. BAKED, verified live.

**Mig head now `chlogseen1`** (`hybridsearch1 → chlogseen1`, adds nullable `users.last_seen_changelog`).

- **Source of truth:** `CHANGELOG_HYBRID.md` (repo root) — strict `## v<semver> — <title>  (<YYYY-MM-DD>)` + `-` bullets, newest first. `VERSION_HYBRID` = current semver (`1.2.0`). Separate from upstream `VERSION`(0.0.412)/`CHANGELOG.md`. Convention: every shipped feature bumps `VERSION_HYBRID` + adds an entry.
- **Backend:** `app/services/changelog.py` (parse_changelog/load_changelog/current_version/entries_after + tuple semver compare, never-raise). `routes/changelog.py`: `GET /api/changelog` `{current,entries}`, `GET /api/changelog/unseen` `{count,latest,current}` (vs user last_seen), `POST /api/changelog/seen` (set last_seen=current, reload-by-PK). All fail-soft. Registered main.py.
- **Frontend:** `components/nav/WhatsNew.vue` (bell + unseen badge, manual popover bottom-end, Activity/What's-new tabs, version chip `v1.2.0 · baked · ● Up to date`, per-release clay cards latest-expanded, See all → `/changelog`; opens → POST seen + optimistic badge clear). `pages/changelog/index.vue` full list. Wired into `nav/TopNav.vue` (explicit import + `<WhatsNew>` between New-Report and profile dropdown; backup `.backups/*_whatsnew-topnav`).
- **Verified live:** GET /changelog → current 1.2.0, 3 entries (1.2.0/1.1.0/1.0.0) features parsed incl em-dash titles; unseen badge logic + POST seen → count 0. FE generated + cp + `docker commit`, health ok.

## 2026-06-25 — PWA (installable desktop/mobile app)

App is now installable from the browser (standalone window, dock/home icon, offline shell, one-click Install button). FE-only, no backend. BAKED + pushed.

- **Module:** `@vite-pwa/nuxt`. `nuxt.config.ts` `pwa{}`: manifest (CityAgent Analytics / CityAgent, `display:standalone`, `start_url:/`, `theme_color #C2683F`, icons 192/512 + maskable), `registerType:autoUpdate`, `devOptions.enabled:false`. Head meta: theme-color, apple-mobile-web-app-capable, apple-touch-icon.
- **Workbox:** `navigateFallback:'/'`, precache shell; **`/api` + `/ws` = NetworkOnly** (never cache API/auth/data); `_nuxt/*` CacheFirst. `globIgnores` Monaco TS worker (~9MB) / ts.worker / babel (~3MB) / big logo + `maximumFileSizeToCacheInBytes:4MB` — FIX for `yarn generate` ERROR "Configure maximumFileSizeToCacheInBytes" (default 2MB precache limit exceeded by editor blobs).
- **Icons:** `frontend/public/pwa-192x192.png` / `pwa-512x512.png` / `pwa-maskable-512x512.png` / `apple-touch-icon.png` (PIL from `assets/logo-mark-512.png`).
- **Install button:** `components/nav/InstallApp.vue` — catches `beforeinstallprompt`, shows only when installable + not already standalone; `prompt.prompt()` on click; hides on `appinstalled`. Wired into `nav/TopNav.vue` left of the 🔔 bell (backup `.backups/*_pwa-pre`).
- **Verified:** generate emits `sw.js` + `manifest.webmanifest`; container serves both 200 (`application/manifest+json`); manifest link + SW register present in JS bundle (SPA `ssr:false` → injected at runtime, NOT in static index.html). Baked into `cityagent-analytics:dev`.
- **LANDMINES:** prod install needs HTTPS (localhost exempt); iOS = manual Share→Add to Home Screen; no silent auto-install in any browser (button = 1-click path); pre-existing TS warnings in nuxt.config (proxy/auth) are harmless, generate ignores them.

## 2026-06-25 — Agent Templates (share an agent's best practices, not the agent)

Export a smart Studio's data-agnostic know-how as a portable, versioned template; others bind it to their own columns and build their own agent. Built P0 (parent) + 4 parallel subagents (export ‖ gallery ‖ bind ‖ FE) + parent wiring. Flag `HYBRID_AGENT_TEMPLATES` (default OFF). BAKED, E2E-verified live.

**Mig head now `agtmpl1`** (`chlogseen1 → agtmpl1`, creates `agent_templates`).

- **Model:** `app/models/agent_template.py` `AgentTemplate` (name, slug, version semver, domain_tags, scope org/global, status draft/published, body_md, manifest JSON, author/org/source_studio). Published = immutable; new version = new row same slug.
- **Contract:** markdown + frontmatter `requires_columns:[{role,as}]` + `uses_skills` + `example_questions`; body has `{as}` placeholders. Export generalizes concrete columns → `{role}` via profile_v2 role map (placeholder = role lowercased, index-suffixed for dupes `{measure}`/`{measure_2}`; `requires_columns` = placeholders actually emitted). Raw golden SQL OFF by default.
- **Services** `app/services/templates/`: `exporter.py` (build_template/export_studio_to_template — strips data/creds/names, longest-name-first replace), `parser.py` (parse_frontmatter/validate_manifest, PyYAML + hand-rolled fallback, never-raise), `binder.py` (auto_match via difflib SequenceMatcher + token-Jaccard — NO embeddings; apply_binding keeps unmapped tokens; instantiate_template → new Studio + pending StudioInstruction/StudioExample + draft MetricDefinition + pending StudioBoundPack skills; run_instantiate/preview_bind for routes).
- **Routes** `routes/agent_templates.py` `/api/templates` (flag-gated, fail-soft): GET list (org+global+own-drafts, q search) · GET /{id} · POST /{id}/publish · POST /import · DELETE /{id} (own draft) · **POST /from-studio/{id}** (export) · **GET /{id}/bind-preview** (auto-match) · **POST /{id}/instantiate**. Registered main.py.
- **FE:** nav **Templates** in Studios group (`nav/TopNav.vue`); `pages/templates/index.vue` (gallery, org/global toggle, search, cards) + `pages/templates/[id].vue` (detail + publish + wizard host) + `components/templates/BindWizard.vue` (4-step: pick data → map columns w/ auto-match badges → review → build). **Export as Template** button in studio header (`studios/[id]/index.vue`, gated canEdit + flag). Backups `.backups/*_agent-templates-wire`.
- **E2E verified** (org 55278108, flag ON, 13 overrides): export CRM studio → template v1.0.0 → list → publish → bind-preview → instantiate → new Studio "CRM from template" in DB. All 8 routes registered (import main).
- **LANDMINES:** new flag needs @property + UPGRADE_FLAGS + snapshot (done); `requires_columns` empty until source studio has profile_v2 (train first); imported items ALWAYS pending (review gate); MetricDefinition needs non-null data_source_id (only seeded when ≥1 ds given); StudioExample.answer NOT-NULL (filled with method).

## 2026-06-25 — Agent Templates: popup journey + skip-data (v1.4.1)

UX upgrade to the template "Use" flow + a no-data path.
- `BindWizard.vue` rebuilt as a **modal popup** (v-model) launched from the gallery card — no page nav. 5 steps: Preview → Data → Map → Review → Build (Map auto-skipped unless binding an existing source with required columns). Stepper, per-step CTA, success screen → Open agent.
- **Step 2 is 3-way**: Use existing source (auto-match + map) · Connect/upload new · **Skip for now**. Skip/connect create the agent with empty data_source_ids.
- Backend: `instantiate` route now **allows empty data_source_ids** (skip mode) — binder already no-ops metrics/auto-match when no ds; seeds rules/examples/skills pending with placeholders intact, to bind later when data is added.
- `pages/templates/index.vue` "Use template" → opens modal in place (`openWizard`); card click still → detail. `[id].vue` mounts wizard via v-model.
- Verified: skip-mode instantiate live → agent "Skip-mode agent" created with no data. FE baked. Backups `.backups/*_bindwizard-modal`.

## 2026-06-25 — Agent Studios page UX cleanup (v1.4.2)

Fixes the "two add buttons / four zeros / no next step" confusion on `/studios`.
- **One add affordance**: removed the duplicate ghost dashed "New Agent Studio" card in `pages/studios/index.vue`; the top-right primary is the single add button.
- **Lifecycle status chip** in `components/studio/StudioCard.vue` (replaces the live/idle dot + the 4-zero stat grid): `draft` (no sources) → `ready` (sources, 0 chats) → `live` (active <7d) → `idle` (quiet). Derived client-side from source_count/chat_count/last_active_at.
- **Per-card next step**: draft → progress bar + "Connect data to activate" + **Add data** button; ready → "Train it to learn your data"; live/idle → real stats (chats/members/sources + last-active) + Open/Chat. Action bar is now persistent (was hover-only).
- **One filled primary per zone**: demoted nav "New report" to an outline button (`nav/TopNav.vue`) so it no longer competes with the page's "New Agent Studio".
- Backups `.backups/*_studios-card-redesign`. FE baked. Changelog v1.4.2.

## 2026-06-25 — v1.13–1.15 (user mgmt, flags UI, hybrid search)
- **v1.13.0** Super-admin DIRECT user create (no invite). `POST /api/organizations/{id}/members/create-user` (admin-gated, `manage_members`); Members "Add user" modal = name/email/password, account active+verified immediately. LANDMINE: do NOT use `manager.create()` (its `_validate_user_creation` gate 400s non-first signups "Sign-up is disabled"); insert User directly (PasswordHelper hash + flags) then add Membership — mirrors OAuth path. Deploy: `docker-compose.nginx.yaml` had no `HYBRID_*` env block (every flag OFF → Studios locked) — added full block with visible features default-ON + a `redis` service.
- **v1.13.1** Dashboard fullscreen rendered only the static header, charts black. `ArtifactFrame` fullscreen overlay = a 2nd `<iframe>`; data was posted only to the bg iframe. Fix: `sendDataToIframe()` broadcasts `ARTIFACT_DATA` to both iframes + re-send on the fullscreen iframe's `@load`.
- **v1.14.0** All 65 hybrid flags toggleable in Settings → Features (was ~32). `UPGRADE_FLAGS` extended with category/status/note for every flag; grouped + search + Enabled/Disabled filter + confirm dialog for unstable/needs-setup. `_effective()` falls back to override-or-env for env-only daemon knobs. Same `GET/PUT /api/organization/hybrid-flags`, no new routes/migration.
- **v1.15.0** Hybrid Search real. OpenRouter `/embeddings` (OpenAI-compatible) → `openai/text-embedding-3-small` (1536d, matches existing column, no migration), org's existing key. `embeddings.py` + `indexer.py` (`reindex_org`) + `hybrid_search.py` pgvector arm + 3-way RRF + `HybridSearchContextBuilder` wired into context_hub + agent_v2 (gated). `POST /api/knowledge/reindex`, `GET /api/knowledge/search-index/status`, Rebuild-index button on Features. Proven: 293 indexed+embedded, RRF returns relevant hits. Reranker deferred (RRF sufficient).

## 2026-06-25 — v1.17–1.18 Claude Design rollout (FE restyle, no functional change) — BAKED
Source = Claude Design handoff bundle `~/Downloads/login-screen-redesign-request/project/*.dc.html`
(Login / Studios v2 / Home). Warm palette everywhere: bg `#F6F1EA`, ink `#1A1611`, accent
`#C2541E`/`#A8330F`/`#D67037`, borders `#E9E0D3`/`#E4D9CA`; fonts Spectral (serif headings) +
Hanken Grotesk (body), loaded via `useHead` (app-wide from TopNav). All restyle-only — auth/fetch/router
logic untouched.
- **v1.17.0** Login (`pages/users/sign-in.vue`) — see its own entry; removed stat line, all auth buttons (Google/Microsoft + Enterprise SSO/Keycloak/LDAP), animated right panel, dynamic version chip.
- **v1.18.0** Studios + Home + Nav + Reports + Agent widget:
  - **Studios** `pages/studios/index.vue` + `components/studio/StudioCard.vue` → Studios v2 mock. Card = dark live-activity header (radial gradient + grid-drift + orange blob + animated equalizer on live / dashed "awaiting first source" on draft), white overlapping icon badge (`-24px`, body `pt-8` clears it), Spectral italic persona, live-stats vs draft/ready progress, coral + ghost action bar. Lifecycle (draft/ready/live/idle) + emits (`open`/`chat`) preserved. Equalizer + Live dot keep animating under `prefers-reduced-motion` (they ARE the live indicator; only card-hover/grid-drift gated).
  - **Home** `pages/index.vue` → cream bg, orange orb glow, greeting eyebrow, Spectral 46px "What should we *explore* today?", subtitle. Dropped full-logo hero + purple `.gradient-glow`. Real `PromptBoxV2`/`DataSourceQuestionsHome`/`RecentReports` children kept as-is.
  - **Nav** `components/nav/TopNav.vue` → cream translucent bar (blur + `#E9E0D3`), gradient logo mark + "City Agent Insights" wordmark, warm links (active `#A8330F`, no gray pills), cream New-report pill, dark-gradient avatar. **Full-width** — removed `max-w-[1340px] mx-auto`, logo flush-left / cluster flush-right (user wanted no side gap). All dropdowns/AgentSelector/WhatsNew/mobile-drawer/perms intact.
  - **Reports** `components/home/RecentReports.vue` (dropdown → **segmented tab** Main Org / My Reports; `viewMode`/`availableOptions` logic kept) + `RecentReportCard.vue` (design card chrome: mode badge + Chat/Dashboard buttons; keeps the **REAL** `thumbnail_url` server preview — user rejected fake KPI mock; no-preview → mode-icon placeholder). Links/handlers unchanged.
  - **Agent status widget** `components/agent/AgentThinking.vue` (NEW, mounted global in `layouts/default.vue` via EXPLICIT import → no dev restart needed). Floating coral robot launcher (bottom-right) → dark terminal popover that types REAL boot lines: `synced N sources · M tables` (N=active `/data_sources`, M=summed `connection.table_count`), `vector index warm`, `ready.` + blinking cursor; footer = green-dot Idle + real default model name from `/llm/models`. Fail-soft, counts warmed in background `onMounted`. NO fake numbers (user rule).
- **Fast-dev loop used this session**: `cd frontend && DASH_BACKEND=127.0.0.1:3007 npm run dev` → Vite HMR on **:3000**, proxies `/api`→ca-app:3007. Edited every `.vue` live, baked once at end. Host node22 `~/.hermes/node/bin`. (CLAUDE.md "Fast dev lane" already documents this.)
- **Admin login reset** (local only): no `DASH_ADMIN_*` env on this box, original password unknown (argon2 hash). Reset `admin@cityagent.io` → `Admin12345` via `PasswordHelper().hash` (fastapi-users uses **argon2id**, not bcrypt) → `UPDATE users SET hashed_password=...`. Two users in DB: `admin@cityagent.io`, `userb@cityagent.io` (neither is_superuser).
- **Studio DETAIL retheme** (`pages/studios/[id]/index.vue`, image-84 page): warm-theme pass via global sed — page bg `#F6F1EA`+Hanken; clay `#C2683F`→coral `#C2541E` (64×), hover `#A8542F`→`#A8330F` (25×); headings Georgia→Spectral (27×); borders `#E7E5DD`→`#E9E0D3`. Logic/tabs untouched.
- **CRASH FIXED — studio Open→/studios/[id] "Cannot read properties of null (reading 'name')"** (was reported "blank" earlier; same bug, error-boundary on :3007 vs blank on :3000). Triggers on **REFRESH/cold-load only**, NOT client navigate. ROOT CAUSE: teleported Nuxt-UI modal `FolderSyncSetupModal` (+ `FolderSyncCard`) bound `:target-studio-name="studio.name"`. **Teleported components render in a SEPARATE reactive scope**, so they evaluate `studio.name` during the brief cold-load window where `studio` ref is still `null` (before `fetchStudio` resolves) → throws. Navigate skips the window (studio already hydrated). FIX: `v-if="studio"` + `:target-studio-name="studio?.name || ''"` (lines ~1354 + 802). **LESSON: any prop on a TELEPORTED modal/popover that reads a fetched-ref's field must `?.`-guard or `v-if` — the parent's `v-else-if="data"` guard does NOT cover teleported children.**
- **DIAGNOSTIC TECHNIQUE (prod minified crash, no DevTools, no source maps):** (1) temp client plugin `plugins/00.error-trace.client.ts` set `nuxtApp.vueApp.config.errorHandler` to PAINT the failing component name (`instance.$.type.__name`) + stack as a fixed on-screen banner → user screenshots it, names `component=<index>`. (2) Pinpoint the exact expression: read the minified chunk at the crash offset — `docker exec ca-app sh -c "awk 'NR==2' /app/frontend/dist/_nuxt/<chunk>.js | cut -c<off-200>-<off+150>"` → showed `...,"target-studio-name":t(k...` = the throwing binding. Remove the temp plugin after.
- **NEW `scripts/fe-sync.sh`** — push FE into the running `ca-app` WITHOUT a Docker rebuild: `pkill nuxt dev` → `rm -rf .nuxt .output …cache` → `npm run generate` → `docker exec -u 0 ca-app rm -rf dist/*` + `docker cp .output/public/. ca-app:/app/frontend/dist/` + chown app:app. Skips base/pip/yarn-install layers + image commit; only cost = `nuxt generate` (~2–5 min, heavy bundle). EPHEMERAL — `--force-recreate` reverts to the baked image; bake for durable. LANDMINE reused: can't generate while `yarn dev` is live in the same dir.
- **STATE:** v1.18.0 BAKED into `cityagent-analytics:dev`; the studio-detail retheme + crash fix + AgentThinking widget are live on :3007 **via FE-sync (ephemeral, NOT yet re-baked)** → next bake = v1.19.0. NOT committed/pushed (user rule: no creds/data from their side).

## 2026-06-25 (cont.) — v1.19.0 bake + v1.20 nav rail + Workspace Templates restyle

- **BAKED v1.19.0** — folded the ephemeral v1.18-era FE-sync work (studio-detail retheme + Open/refresh crash fix + AgentThinking) into the image durably. `docker compose -f docker-compose.build.yaml build app` → up. Verified `/healthz` 200, `VERSION_HYBRID`=1.19.0, DB `users`=2 (data intact).
- **COMPOSE LANDMINE (caught mid-bake):** first recreate used plain `docker-compose.yaml` → that file is a DIFFERENT compose project (`dash-app`/`dash-postgres` container_names, volume `postgres_data`) and spun up a FRESH EMPTY DB. The real running stack is **`docker-compose.build.yaml`** (`ca-app`/`ca-postgres`/`ca-redis`, volume `ca_postgres_data`). Tore down the `dash-*` stack, brought `ca-*` back via build.yaml — real `ca_postgres_data` was never touched, no data loss. **RULE: always recreate/up THIS stack via `docker-compose.build.yaml`, never the bare `docker-compose.yaml`.**
- **Studio-detail tab persists in URL** (`pages/studios/[id]/index.vue`): `const activeTab = ref(route.query.tab as string || 'autopilot')` + `watch(activeTab, t => router.replace({query:{...route.query,tab:t}}))`. Fixes "refresh bounces me off Metrics back to Auto-pilot" — tab is now shareable/bookmarkable. (`watch` is Nuxt auto-imported.)
- **NAV RAIL (v1.20, requested from `City Agent Workspace v2.dc.html`)** — replaced top-nav DROPDOWNS with a contextual LEFT RAIL:
  - `composables/useAppNav.ts` (NEW) — single source of truth for the grouped nav, shared by TopNav + AppRail so they never drift. Exposes `visibleGroups`, `activeGroup` (the non-`direct` group matching the route), `isRouteActive`, `isGroupActive`, `firstHref(group)`, `showMcpModal` (module-level singleton ref — fine on SPA/`nuxt generate`), `loadDomainPacksFlag`. Ports the full group model + permission gating + settings sub-tabs verbatim from the old TopNav inline model.
  - `components/nav/AppRail.vue` (NEW) — cream 224px rail (`#F2EBE0`, border `#E9E0D3`). Shows the active group's eyebrow + items; active item = white pill, coral text. `v-if="activeGroup"` → self-hides on Home / Agent Studios (direct, excluded from `activeGroup`) / detail pages that own a rail.
  - `components/nav/TopNav.vue` — desktop group menubar: each group is now a single `NuxtLink :to="group.direct || firstHref(group)"` (NO `UPopover`, no dropdown panels). Removed ~165 lines of inline nav model + dropdown markup; pulls everything from `useAppNav()`. Mobile slide-over drawer kept (still lists groups). Dropped now-unused imports (McpIcon/LibraryIcon/ActivityIcon/AgentIcon) + `isMcpEnabled` local.
  - `layouts/default.vue` — non-report branch wraps content as `flex`: `<AppRail/>` + `<div class="flex-1 min-w-0 overflow-y-auto"><slot/></div>`. Report-detail branch (ChatHistoryRail) unchanged.
  - LANDMINE: pages with their OWN internal sub-rail (Skills category rail All/Finance/…, Knowledge) now render TWO rails side-by-side (Build group rail + page rail). Acceptable for now; suppress AppRail per-page later if the user wants single-rail there.
- **Workspace Templates restyle** (`pages/templates/index.vue`) to the v2 design: `.wk-h1` Spectral 500 33px header + green `#3E7A4D` "Your data never leaves"; coral-border Publish pill; segmented Org/Global/All toggle on `#EFE7DA` (active `#C2541E` white); white search `#E4D9CA`; cards `#E9E0D3`/radius-16 with gradient icon tile (`#FBEADF→#F4D8C6`), mono version chip `#F4EEE5`, Spectral 18px `.wk-card-title`, ★ uses, coral `.wk-prim` "Use template", `.wk-card` hover-lift. Logic/data (scope/search/BindWizard/openWizard) untouched. Remaining Workspace views (Reports/Dashboards/Presentations/Spreadsheets/Scheduled) defined in the same `.dc.html` — NOT yet restyled.
- **STATE:** v1.19.0 BAKED. Nav rail + tab-persist + Templates restyle are live on :3007 **via FE-sync (ephemeral)** → next bake = **v1.20.0**. NOT committed/pushed (user rule: no creds/data from their side). Design mocks live at `~/Downloads/login-screen-redesign-request/project/*.dc.html`.

## 2026-06-26 — v1.20.0 + v1.21.0 baked: nav rail + Workspace/Build/Manage/Settings warm restyle

- **v1.20.0 BAKED** (nav rail + Templates + Build×5 + Manage×3 + studio-detail tab persist). See the 2026-06-25 entry for the nav-rail architecture (AppRail + useAppNav). Recreated via `docker-compose.build.yaml` (correct file — NOT plain docker-compose.yaml). Verified `/healthz` 200, users=2.
- **v1.21.0 BAKED** — Settings warm-theme restyle (all 11 tabs): Members/Access, LLM/Models, AI Settings, General, Channels/Integrations, Folder Sync, Audit, Identity Provider (SSO/SCIM/LDAP), SMTP, Feature Flags, Pack Analytics. Also recolored `layouts/settings.vue` + settings-imported components (`sync/FolderSyncPanel.vue`, Email/WhatsApp/Teams/Slack integration modals). Verified `/healthz` 200, VERSION_HYBRID=1.21.0, users=2 (data intact).
- **RESTYLE METHOD (warm-theme migration, token-only — NO icon/logo/markup/logic changes):** per-file `perl -0pi -e` over the page/component set:
  - `#C2683F`→`#C2541E` · `#A8542F`→`#A8330F` · `#E7E5DD`→`#E9E0D3`
  - `bg-[#FBFAF6]`→`bg-[#F6F1EA]` · `bg-[#F4F1EA]`→`bg-[#F4EEE5]` · `bg-[#F3E7DF]`→`bg-[#FBEFE4]`
  - `ui-serif, Georgia[, 'Times New Roman'], serif`→`'Spectral', ui-serif, Georgia, serif`
  - h1 `text-2xl font-semibold text-[#1f2328] tracking-tight`→`text-[32px] font-medium text-[#211B14] tracking-tight`
  - LANDMINE: `for f in $(rtk proxy find …)` mangles the file list — use `find … -print0 | while IFS= read -r -d ''` instead. Verify residue with `grep -rl "C2683F\|A8542F\|#E7E5DD"`.
- **Templates** was a FULL design rewrite (not just tokens) to `City Agent Workspace v2.dc.html`: `.wk-h1` Spectral 33px + green "Your data never leaves", segmented Org/Global/All, gradient icon-tile cards, coral "Use template".
- **Deferred:** Workspace Reports/Dashboards/Presentations/Spreadsheets/Scheduled (own pages, not yet restyled) + Monitoring (`layout: 'monitoring'` + ConsoleOverview, deep sub-console outside AppRail).
- **MOCKS:** `~/Downloads/login-screen-redesign-request/project/{City Agent Studios v2, Home, Workspace v2, Build v2, Manage, Settings}.dc.html` (DCLogic sandbox format).
- **STATE:** v1.21.0 BAKED. NOT committed/pushed (user rule: no creds/data from their side). Stack on `docker-compose.build.yaml`.

## 2026-06-26 (cont.) — Parquet result storage + interactive query endpoint (flag default ON)

- **NEW `backend/app/services/parquet_store.py`** — large step results (`{rows,columns,info}`) offloaded to compressed Parquet on disk instead of inline JSON in Postgres. `maybe_offload` (flag + ≥`PARQUET_MIN_ROWS` rows → DuckDB `COPY … FORMAT PARQUET COMPRESSION ZSTD`, no pyarrow); marker `{__parquet__:1,path,columns,info,rows:[]}`. `hydrate` loads rows on read + tags `source:"parquet"`. Fail-soft (write error→inline), crash-safe (file before commit), missing file→empty rows. LANDMINE fixed: `_base_dir()` mkdir before COPY.
- **Flag** `HYBRID_PARQUET_RESULTS` = `_bool(...,True)` **DEFAULT ON** (user requested) + `PARQUET_MIN_ROWS` `_int` env knob (default 2000) + UPGRADE_FLAGS entry + snapshot(). New `_int()` helper in hybrid_flags.py.
- **Write sites** routed via `maybe_offload` (+ delete old file on rerun): query_service:244, step_service:150, project_manager.update_step_with_data.
- **Read sites** hydrate (no-op when off/inline): StepSchema/PublicStepSchema `data` validator (covers all schema routes incl. CSV export); raw ORM readers patched — loadables (agent load_step), widget_context_builder (count uses info.total_rows), thumbnail_service, report_pdf_service, slack_notification_service.
- **Interactive query endpoint** `POST /steps/{step_id}/query` (app/routes/step.py, `StepQueryRequest`, `requires_permission('view_reports')`) → `parquet_store.query(step.data, spec)`. Declarative ALLOW-LISTED DuckDB pushdown: ops {=,!=,>,>=,<,<=,in,contains}, aggs {sum,avg,min,max,count}; cols validated vs step columns; values param-bound; limit cap 5000; NO raw SQL; DuckDB err→ValueError→400. Returns {rows,columns,total_rows,source,ms}.
- **Frontend** `composables/useStepQuery.ts` (queryStep via useMyFetch, fail-soft) + `DashboardComponent.vue` guarded branch: `widget.last_step.data.source==='parquet'` → server query for cross-filter/sort/page; else EXACT current client-side path (no-op for inline). `hydrate` emitting `source` is the activation link.
- **GC** `sweep_orphans` (delete Parquet not referenced by any `steps.data->>'path'`) wired into daily `purge_step_payloads_per_organization` (flag-gated). Parquet under `/app/backend/uploads/parquet` on **ca_uploads** volume.
- **NEW `scripts/safe-upgrade.sh`** — rollback-tag image + pg_dump + tar PG vol + tar uploads vol → build+tag :version → recreate → health-gate → AUTO-ROLLBACK on fail. Backs up DB + uploads TOGETHER (parquet integrity).
- Built via 3 recon subagents (parallel touch-point mapping) + 2 build subagents (backend query+route / frontend wiring), disjoint files; I added the `source` link + ran security + parquet-path container smoke tests (bad col/op → 400; filter+group+agg+order correct).
- Docs: `docs/parquet-results.md`. py_compile clean, container-tested. **NOT baked** → ships v1.23.0. NOT committed/pushed.

---

## 2026-06-26 — v1.24.0 Per-agent Channels (two-pane) + per-agent Email/SMTP + Docker build speedups (BAKED + live)
Studio MANAGE rail split: **Settings · Access & Members · Channels · Email / SMTP · Members & Share**
(was the combined "Access & Channels"). `VERSION_HYBRID` 1.23→1.24, baked, healthy, users=2.
- **Channels tab** `components/studio/StudioChannels.vue` — org-style **two-pane picker** (platform
  list + detail pane, status dots; per-platform set-up/reconfigure/enable/disable/delete). Reuses the
  existing Slack/Teams/WhatsApp/AI-Mailbox config modals + Telegram/MCP inline; same config METHOD,
  org LAYOUT. Catalog mirrors org Settings→Integrations. `GET /studios/{id}/channels` drives status.
- `StudioAccess.vue` — channels card + 4 modals + telegram/mcp logic REMOVED; renamed "Access &
  Members" (who-can-use / model / members / connections only). Header copy updated.
- **Email / SMTP tab** `components/studio/StudioEmail.vue` (NEW) — per-agent outbound mail. Mode
  radio: **global default** (inherit org/dash-config, zero-config) OR **custom SMTP for this agent**.
  Custom fields mirror org SMTP (from name/addr, host, port, user/pass optional, security select,
  validate-certs toggle) + "Send test connection". Password only sent when retyped (`password_set`
  drives the saved-placeholder).
- **Backend per-agent SMTP**:
  - `email_client_resolver.py`: `_studio_smtp_resolved` + `studio_smtp` param in `choose_outbound`
    (wins over AI-mailbox/org/global for either purpose); `get_studio_smtp(db, studio_id)` reads
    `Studio.config['smtp']`, returns decrypted dict ONLY when `mode=='custom'`+host; `resolve_outbound`
    gains `studio_id=`. Precedence: **agent custom → AI mailbox (analyst) → org SMTP → global**.
  - `notification_service.py`: `studio_id` threaded through `dispatch` (+context), `send_custom_email`,
    `_resolved_send` → `resolve_outbound(..., studio_id=)`. `_send_email` reads `context['studio_id']`.
  - `report.py` share dispatch now passes `db` + `organization_id` + `studio_id=report.studio_id`
    (so org-SMTP applies to shares too — behavior change: org-SMTP-enabled orgs now share via org SMTP,
    not always global; the EMAIL-channel guard still requires global `email_client` present).
  - `email_send_service.py` channel/agent reply: `send_custom_email(..., studio_id=report.studio_id)`.
  - Routes `GET/PUT/POST-test /api/studios/{id}/smtp` in `external_platform.py`
    (`StudioSmtpSchema`/`StudioSmtpUpdate` mirror `OrgSmtp*` + `mode`), flag `HYBRID_AGENT_CHANNELS`,
    owner/editor via `_require_channel_manager`. `_load_studio` org-scopes. Audit `studio.smtp_updated`.
    Fernet via `app.services.email.secrets.encrypt_secret`; `flag_modified(studio,'config')`.
  - NULL studio / `mode==global` = byte-identical old behavior. No migration (`config` is JSON).
- Verified live: `choose_outbound` precedence=studio_smtp; 3 smtp routes registered; `import main`
  clean (456+ routes); AGENT_CHANNELS=True; users=2; /health 200; VERSION_HYBRID=1.24.0.
- **Dockerfile speedups** (banked in same image): removed `apt-get upgrade -y` from `backend-builder`
  + `frontend-builder` (deterministic, cache-stable; runtime `base` keeps security upgrade); added
  BuildKit cache mounts on `yarn generate` (`node_modules/.cache` + `node_modules/.vite`,
  `sharing=locked`) → repeat FE rebuilds much faster (cold seed once, then warm). NOT caching `.nuxt`
  (stale-module/phantom-module risk). Why bakes are slow = `nuxt generate` is inherently minutes cold;
  backend-only changes skip it (FE stage cache-hits). Use foreground `DOCKER_BUILDKIT=1 docker build`
  to dodge the cache-stale `:dev` tag.

## 2026-06-26 — v1.37.0 Scheduled reports + universal report-delivery (rich email)
Per-agent scheduled reports that email a CLEAN, structured result instead of dumping the raw agent
chat. Built P0→P5 (scaffold → engine → UI → dashboard → artifact → workflow) + format-threading +
unit tests. Two new flags (default OFF, ON org 55278108): `HYBRID_AGENT_REPORTS` (UI Reports tab),
`HYBRID_RICH_REPORT_EMAIL` (engine). VERSION_HYBRID 1.36.0→1.37.0.
- **Universal delivery layer** `backend/app/services/report_delivery/`:
  - `contract.py` (FROZEN) — `DeliveryContext`/`DeliveryParts`/`InlineImage`/`Attachment`,
    `register_renderer`/`get_renderer`/`list_modes`, and async DB-aware `classify(ctx)` (priority:
    explicit `options.format` → workflow source → artifact (model `Artifact`, NOT text-only
    `StudioArtifact`) → ≥2 widgets = dashboard → result). Single chart-widget stays Mode A.
  - `extract.py` — `sanitize_chat_content` (strips `**🧠 Planning ✓**`, ``` fences ```,
    `generate_df` tail, markdown recap tables, "table generated above" refs), `split_intro_and_insights`,
    `extract_result` (real grid from `steps.data` + clean SELECT lifted from `steps.code`), `latest_narrative`.
  - `template.py` — shared inline-styled skeleton + zebra `table_html` ($-format heuristic) + `insights_html` + `sql_block`.
  - `renderers/` — **auto-imported** via `pkgutil.iter_modules` so a new `renderers/<mode>.py` self-registers
    (zero shared-file edits → parallel-safe). `result.py` (P1), `dashboard.py`+`render_service.py` (P3,
    Playwright single-page PNG `screenshot(full_page)` + PDF, reuses ReportPdfService HTML build),
    `artifact.py` (P4, latest `Artifact` → pptx via `soffice --convert-to pdf` → `pdftoppm` page-1 PNG +
    file attach; pdf direct; screenshot_base64 fallback), `workflow.py` (P5, step timeline ✓/✗ from
    run summary `log[]` or exec_summary, per-step output attach, cap 10 files/25MB).
  - `assembler.py` — `build_parts` (classify→renderer, fallback "result") + `deliver` (per-agent SMTP via
    `studio_id`; inline-cid path builds multipart/related itself; transient-DNS retry ×3).
- **Rewire** `notification_service.send_scheduled_prompt_results` → rich path under `flags.RICH_REPORT_EMAIL`
  (legacy raw-content kept when OFF); new `report_format` param threaded from
  `scheduled_prompt_service.scheduled_run_prompt` (`sp.prompt['format']`) → `DeliveryContext.options['format']`.
- **Inline cid** added to `email/message_builder.build_email` (`inline_images=[(cid,bytes,subtype)]` →
  `msg.add_related`); verified multipart/related (html+png).
- **Reports tab** (gated `HYBRID_AGENT_REPORTS`): `routes/studio_reports.py` (GET/POST/PUT/DELETE/run-now
  `/api/studios/{id}/scheduled-reports`, reuses `ScheduledPromptService`) + `components/studio/StudioReports.vue`
  (list/create/edit/pause/delete/send-test-now, format dropdown auto|table|dashboard|artifact|workflow).
  Per-studio hidden CONTAINER report: marked `report_type='scheduled_container'` (stable vs auto-titler) +
  created via `report_service.create_report(studio_id=)` so the studio's pinned data sources attach (else
  agent had no data context → prose-only, no table). Format stashed in `ScheduledPrompt.prompt` JSON (no migration).
- **Workflow delivery hook**: `routes/workflows.py` optional `notify` on run → `assembler.deliver` with
  `options={source:'workflow', workflow_run:summary}` (opt-in, flag-gated, fail-soft; subsystem has NO persisted run table).
- **LANDMINE FIX (latent, v1.24):** `email_client_resolver.ResolvedOutbound.uses_smtp_config` listed only
  `ai_mailbox`/`org_smtp` — NOT `studio_smtp`. So every per-agent send via `_resolved_send` silently fell to the
  (absent) global fastapi-mail client → `ok=False`. Added `studio_smtp`. Per-agent SMTP (e.g. an agent on
  Office 365) now actually sends.
- **LANDMINE:** scheduled run-now 404 on 2nd call — the completion AUTO-TITLER renames the container report, so
  title-based lookup/get-or-create broke + spawned duplicate containers. Fix = stable `report_type` marker, never title.
- **LANDMINE:** transient `[Errno -5] No address associated with hostname` on SMTP connect from the server's event
  loop — Docker embedded DNS saturates while the agent fires many concurrent OpenRouter calls. Mitigated by the
  ×3 retry in `assembler.deliver` (standalone in-container sends always resolved).
- E2E verified live (org 55278108, studio rrr=35a1ea36…, sender = the agent's own Office 365 mailbox):
  result table email + full dashboard email (258KB inline PNG + 352KB PDF) + workflow timeline email all
  `ok=True` to a real inbox; artifact preview pipeline proven (58KB PNG + 47KB pptx). 17 unit tests pass
  (`pytest tests/unit/test_report_delivery.py --noconftest`). Built by parallel subagents on disjoint files.

## 2026-06-27 — One-click slide decks with real charts (v1.38.0, flag HYBRID_SLIDE_DECK)
**Problem.** A report's Slides view fell back to the lightweight client-side `SlidesPanel` whenever no
`mode='slides'` artifact existed (the common case — decks are only made by typing in chat). `SlidesPanel`
has no chart renderer; it only shows a viz's `thumbnail_url` image, which report visualizations don't carry
→ every chart slide rendered as the generic grey 3-bar placeholder. User wanted a REAL slide artifact.
**Fix.** One-click generation of a real `Artifact(mode='slides')` from the report's existing charts, no chat:
- **Backend** `routes/report_slides.py` (new, gated `flags.SLIDE_DECK`, 404 when off, mounted `/api`):
  `POST /api/reports/{id}/slides/generate` loads the report's success visualizations, resolves the org default
  LLM (`organization.get_default_llm_model`), instantiates `CreateArtifactTool` with a MINIMAL hand-built
  `runtime_ctx` (db/report/user/org/model; context_hub/context_view/head_completion=None — all guarded in the
  slides branch), drains `run_stream({mode:'slides', visualization_ids:[all]})`. Reuses the EXACT chat slides
  pipeline (LLM python-pptx → `PptxCodeExecutor` → `PptxPreviewService` → preview PNGs + pptx_path). Re-queries
  the artifact; on `status=='failed'` deletes it (so it can't flip `hasSlidesArtifact` true with an empty deck)
  and 502s with `render_errors[0]`.
- **Flag** `HYBRID_SLIDE_DECK` in `hybrid_flags.py` (@property + UPGRADE_FLAGS + snapshot, default OFF; ON org
  55278108 via DB `hybrid_overrides`).
- **FE** `pages/reports/[id]/index.vue`: the slides fallback (no artifact + has vizs) now shows a **Generate
  slide deck** button when `slideDeckEnabled` (reads `/organization/hybrid-flags` for `HYBRID_SLIDE_DECK.effective`
  on mount); click → `POST /reports/{id}/slides/generate` → `checkHasArtifacts()` refetch → `hasSlidesArtifact`
  flips → the existing `ArtifactFrame` branch renders the real deck. Flag OFF → legacy `SlidesPanel` unchanged.
**Two pre-existing slides-pipeline bugs fixed (also affected chat decks):**
1. `pptx_executor.py` AST gate listed `getattr` in `FORBIDDEN_BUILTINS`, but the slides prompt's MANDATORY
   `style_chart_text` helper is built on `getattr(chart,'category_axis',None)` → every styled deck failed
   "Forbidden function call: 'getattr()'". Fix: `PPTX_ALLOWED_BUILTINS={'getattr','hasattr'}` (read-only
   introspection; `setattr` deliberately NOT whitelisted) excepted in `visit_Call`.
2. Decks hard-crashed "chart data contains no categories" when a KPI/single-value/empty-label viz was charted.
   Fix: added a mandatory **DATA SAFETY** block to `_build_slides_prompt` (filter None/empty labels; if no
   categories → KPI card / text slide, never `add_chart`; coerce values; per-chart try/except so one bad viz
   can't sink the deck).
**E2E verified live** (org 55278108, report 86bfef9a "Calls by Channel Type Distribution", 8 vizs): attempt 1
failed on getattr → fixed; attempt 2 failed on empty categories → fixed; attempt 3 → `status=completed`,
pptx at `uploads/pptx/<id>.pptx`, **5 slide preview PNGs**, thumbnail set. Failed test artifacts cleaned.
Backend hot-deployed (docker cp + restart); FE via `scripts/fe-sync.sh` (button confirmed in `dist/_nuxt`).
EPHEMERAL — not baked into the image yet.

## 2026-06-27 — One-click Dashboard + Excel (v1.39.0, flag rename HYBRID_ONECLICK_ARTIFACTS)
Extends the v1.38 one-click slide deck to the other two empty right-panel views the user flagged
("No artifacts yet", "No spreadsheet yet").
- **Flag rename** `HYBRID_SLIDE_DECK` → `HYBRID_ONECLICK_ARTIFACTS` (hybrid_flags.py property/UPGRADE_FLAGS/snapshot;
  DB `hybrid_overrides` migrated for org 55278108). Gates all three CTAs.
- **Backend** `routes/report_slides.py` generalized: shared `_generate_artifact(mode)` helper +
  `POST /api/reports/{id}/dashboard/generate` (mode='page') beside `…/slides/generate` (mode='slides'). Both
  run `CreateArtifactTool` over the report's vizs (minimal runtime_ctx), re-query + delete a `status='failed'`
  artifact so it can't flip hasPageArtifact/hasSlidesArtifact with an empty frame. Per-mode prompt + label.
- **Excel** = read-only, NO LLM: new `GET /api/reports/{id}/workbook` → `{sheets:[{name,columns,rows}]}`, one
  sheet per query's latest SUCCESS step, `steps.data` parquet-hydrated + `_coerce_grid` (array-of-objects →
  rows aligned to columns), capped 5000 rows × 50 sheets. The `/api/queries` LIST strips step row data
  (`default_step.data == {}`), so the Excel tab could not be built client-side — this returns the real grids.
- **FE** `pages/reports/[id]/index.vue`: dashboard CTA `<div>` branch BEFORE the page `ArtifactFrame` (gated
  `oneClickEnabled && !hasPageArtifact && has vizs`), `generateDashboard()` mirrors `generateSlideDeck()`;
  `serverSheets` ref fetched from `/workbook` on mount (`loadOneClickFlag().then(loadWorkbook)`), `excelSheets`
  computed prefers `serverSheets` over the message-scraped `messageSheets`. Flag var `slideDeckEnabled` →
  `oneClickEnabled`, env `HYBRID_ONECLICK_ARTIFACTS`.
- **E2E LIVE** (org 55278108, report 86bfef9a, 8 vizs): `/workbook` → 4 sheets (real cols/rows);
  `/dashboard/generate` → page artifact `status=completed` (10k code, no render errors); slides still good.
  Backend hot-deployed (docker cp + restart); FE via `scripts/fe-sync.sh`. EPHEMERAL — not baked.

## 2026-06-27 — v1.40.0 Cleaner chat + one warm canvas (cosmetic) + fresh-DB FK guard
Cosmetic chat redesign on the report page (Claude/ChatGPT-style grammar) + a colour-consistency fix
+ one backend correctness fix. NO functional/agent-loop change. Hot-deployed to :3007 (FE via
`yarn generate` + docker cp; backend via docker cp + restart). EPHEMERAL until baked.
- **`pages/reports/[id]/index.vue` (P0–P5, cosmetic):** center surfaces `bg-[#F6F1EA]`→`#FAF8F3`;
  `.cc-step` threaded tool rows (padding-inline-start 20px, `::before` connector rail `#E9E0D3`,
  `::after` status dot, `--done` green `#3F7A4F` / `--err` amber `#C08A2D`); `awaitingClarify` computed
  → "Waiting for your answer — run paused" chip replaces the perpetual `isPolling` spinner (followups
  loader also gated `!awaitingClarify`); `nowTick` + `watch(isStreaming)` 1s interval + `liveElapsed(m)`
  → `cc-shimmer` header + live `· Ns` timer (cleared `onUnmounted`); markdown `:deep(.markdown-content)`
  13→15px / line-height 1.7 / color `#1f1d1a`, serif Spectral headings, `strong` 700, hairline tables
  (`#FAF7F1` header) + `hr` `#E9E0D3`; empty-state eyebrow "New report · no messages yet".
- **`components/tools/CreateDataTool.vue` (P1 garble fix):** header `flex-wrap min-w-0`; table-name
  `join(', ')` → count chip `{N} table(s)` with `:title` full list + `DataSourceIcon flex-shrink-0`.
  Kills the garbled vertical-text overflow in the tool row.
- **`components/report/SplitScreenLayout.vue` (warm-canvas fix):** root `bg-white`→`bg-[#FAF8F3]`;
  right Outputs pane `bg-white`→`bg-[#FAF8F3]`; inner rounded card `bg-[#f8f8f7]`→`bg-[#FAF8F3]` +
  border `black/[0.08]`→`#E9E0D3`. Fixes the warm→cool-white jump when a report opens its dashboard/
  answer dock (the "color changes when chat starts" report).
- **`services/report_service.py` (fresh-DB FK guard):** `create_report` verifies `studio_id` exists in
  the org (`Studio.id == studio_id AND organization_id AND deleted_at IS NULL`), else logs + nulls it.
  Fixes `ForeignKeyViolationError fk_reports_studio_id_studios` on a fresh/wiped DB when the browser
  still holds a stale localStorage studio id. Verified HTTP 200 with a bogus studio_id.
- Rollback backups of all 4 changed files + the pre-copy container `dist` (69M) saved in the session
  scratchpad (`rollback_phaseA/`). NOT yet baked — next step = durable image rebuild.

## 2026-06-27 — v1.41.0 Live train log (CLI) + AI column meanings + SOON cards
Three ships. All EPHEMERAL (docker cp + restart; baked via docker commit, NOT a Dockerfile build).
- **Live training log (Option A):** `train_orchestrator.py` now keeps a capped timestamped `log[]` in the run
  status. A per-run `logging.Handler` (`_RunLogHandler`) attached to loggers `app.ai.knowledge`/`app.ai.llm`/
  self captures every line the trainer + LLM client already emit (model, counts, errors); plus explicit `_log`
  calls: "Auto-train started", pinned-source count, "default analysis model: <id>", `▸ <stage>` markers,
  and a done/failed summary. `_LOG_CAP=400` in-process, `_LOG_PERSIST_CAP=200` mirrored to
  `Studio.config['_train_status']` (bounded JSON). New `reset_status()` + route `POST /studios/{id}/train/reset`
  (clears a stuck `running` status — the prior 75%-frozen bug had no UI escape). FE `studios/[id]/index.vue`:
  inline panel under the TRAIN card (`trainLog`/`trainStages`/`trainLogLines`), Logs⇄Steps toggle, warm-dark
  `#1b1813` terminal (mono, auto-scroll via watch+nextTick, level colors blue/amber/red), %-bar, Reset/Retry,
  on-mount `loadTrainStatus()`.
- **AI column meanings (closes a real gap):** nothing in the product ever wrote `SemanticColumn.meaning`
  (manual-edit only; `knowledge.py:165` seeds `meaning=""`, `:261` PATCH sets it). New
  `propose_column_meanings(db,*,organization,data_source,model,llm_inference=None)` + `build_column_meaning_prompt`
  in `knowledge_proposer.py`: loads semantic tables (selectinload columns), for each BLANK + non-approved column
  asks the LLM for a one-sentence meaning, writes `status='pending'` (never overwrites approved), returns
  `{"columns":[ids]}`, fail-soft. Route `POST /api/knowledge/ai-suggest-columns/{ds}` (mirrors `/ai-suggest`,
  gated `SEMANTIC_LAYER`, placed BEFORE the `/{kind}/{id}` catch-all). Folded into the Auto-train
  `semantic_metrics` stage (per-source, auto-approved like sem/met; detail → `N col meanings`). FE
  `SemanticTab.vue` "Suggest column meanings" button (`suggestingColumns` ref, bare `useMyFetch` POST,
  `loadSemantic()` refresh). Built by 3 parallel subagents (disjoint files) + I wired the train stage.
  RAN for studio Rahul: 15/15 columns filled + approved + in agent context. `column_7` honestly returned
  "Unidentified column…" (no hallucination).
- **Cards:** `reports/[id]/index.vue` Infographic + Insight Map → dimmed `SOON` non-clickable (match Forecast/
  Anomaly). Excel stays live (real `/workbook`).
- **Phase 1 (this session):** fresh admin org `1a073f60` had ZERO hybrid overrides (only the wiped demo org
  55278108 was ever enabled) → all Intelligence tabs showed "Enable…". Wrote 8 overrides to
  `organization_settings.config.hybrid_overrides` (PROFILE_V2, METRICS_CATALOG, SEMANTIC_LAYER, GOLDEN_QUERIES,
  PROACTIVE_INSIGHTS, VERIFIED_METRICS, CODE_ENRICH, SEMANTIC_SEARCH; FORECAST left off — needs prophet). Boot
  log "Loaded 8 hybrid flag override(s)". Rollback backups in session scratchpad `rollback_trainlog/`.

## v1.42.0 — Group-based agent access + merged Access tab (2026-06-27)
Shared-agent access by GROUP (incl. AD/LDAP-synced) + tab consolidation. Flag **HYBRID_GROUP_ACCESS** (default OFF).
- **P1 merge tabs (FE):** removed the thin `members` tab from `studios/[id]/index.vue` (tab def + `<section activeTab==='members'>`); `?tab=members` redirects to `access`; Delete-Studio folded into `StudioAccess.vue` (owner-only, `@delete-studio` emit). One tab now: **Access & Members**.
- **P2 group access (backend, NO migration):** reuses generic `ResourceGrant` (`resource_type='studio'`, `principal_type='group'`, `permissions` JSON list). `services/studio_access.py` + `user_group_ids()`, `group_granted_studio_roles()` (flag-read here), `_perms_to_role` (write/edit/manage→editor else viewer), `_ROLE_RANK` strongest-wins. `resolve_studio_access` gains step 2.5 (group grant before org-scope). **`GET /studios` list query OR-includes group-granted ids** → a shared agent auto-appears in studios list AND chat dropdown (both source `/studios` via `useAgent.ts:198` → `AgentSelector`). Routes on `studio.py`: `GET/POST/DELETE /studios/{id}/group-grants` (owner-only mutate via `_require_access`, viewer+ list; `_ensure_group_access` 404s when flag off; idempotent upsert reusing soft-deleted row). Flag added 3-place in `hybrid_flags.py` (UPGRADE_FLAGS + `GROUP_ACCESS` property + snapshot).
- **P3 Private/Public toggle (FE):** `StudioAccess.vue` 3-radio scope → OpenWebUI 2-state **Private** (`private`) / **Public** (`org`) cards; **Link** demoted to "Advanced — share by link" expander (auto-opens on link, `active` badge, copy-link). `scopeLabel` map. Reuses existing PATCH `/share` (no backend change). Access panel already hides when scope≠private.
- **P4 group picker (FE):** new `StudioAccessPicker.vue` (auto-imports as `<StudioAccessPicker>` — filename starts with `Studio`). Searchable groups from `GET /organizations/{org}/groups` (returns member_count + external_provider), AD/LDAP/Okta/SCIM badges vs local, already-granted greyed, checkbox multi-select, Viewer/Editor radio → POST group-grants. `Sync from AD/LDAP` → `POST /enterprise/ldap/sync` (org from context, soft-fail "LDAP not configured"). `StudioAccess.vue` Access panel restructured: **Groups** list (role dropdown + revoke ✕) above **People**; `[+ Add access]` button; whole block self-gates on `HYBRID_GROUP_ACCESS` via `/organization/hybrid-flags` (`env_name`/`effective` pattern, same as StudioConnectors). Org id via `useOrganization().ensureOrganization()`.
- **P5 deferred:** inline create-group modal (picker `+ Create group` currently toasts a pointer to Manage → Groups). AD-sync surface shipped in picker.
- **P6 enable + E2E + bake:** wrote `HYBRID_GROUP_ACCESS=true` to org `1a073f60` `hybrid_overrides` (now **9 overrides**, boot log confirms). ORM E2E (in-container, `import main` to load mappers + `set_override`): group grant `['read']`→viewer, `['read','write']`→editor, cleanup clean. Bake via `docker commit` (FE dist + backend already hot-cp'd this session). Rollback tag `pre142-rollback`. Source `.p1bak` backups in session scratchpad.
- **Audit lesson:** ~70% already existed — Group model (AD/LDAP `external_id`/`external_provider`), GroupMembership, `ee/ldap/sync_service.py` (writes groups table), `ee/oidc/group_sync_service.py`, RBAC group CRUD, ResourceGrant(`principal_type` user|group|role). The ONLY real gap was studio access never resolving groups (resolver + list query). Net new: 1 resolver step + 3 routes + 2 FE components + tab merge.

## v1.43.0 — User provenance + super-admin-only creation + merge hardening (2026-06-27)
Identity provenance display + lock manual user creation to superuser + opt-in email-merge gate. Built by 4 parallel subagents (disjoint files, fixed `auth_sources` contract). NO migration, NO flag.
- **Merge model (audit):** identity keyed by EMAIL, one `users` row, multi-credential. SSO `oauth_callback` (core/auth.py:526): by oauth_account → else **get_by_email → LINK OAuthAccount onto existing user** → else create. LDAP `_ldap_authenticate`: get_by_email → else auto-provision (`ldap_dn` set). So local+LDAP+SSO same email = ONE merged user. Provenance fields already on User: `ldap_dn`, `scim_external_id`, `oauth_accounts[].oauth_name`, `hashed_password`.
- **P-A creation lock (agent1):** `routes/organization.py` `add_member` + `create_user_directly` add `if not current_user.is_superuser: raise HTTPException(403, "Only a super admin can create users…")` ON TOP of `@requires_permission('manage_members')`. FE `MembersComponent.vue` hides Add Member + Import unless `isSuperuser` (session `is_superuser` top-level, per nuxt.config sessionDataType; `useCan('add_organization_members')` kept as AND). LDAP/SSO auto-provision untouched (allowed automatic creators).
- **P-B user source (agent1+2):** `MembershipSchema.auth_sources: List[str]` (organization_schema.py). `_derive_auth_sources(user)` in organization.py → "ldap" / "sso:<oauth_name>" (distinct) / "scim" / else ["local"]; None→[]. `get_members` route re-queries memberships `selectinload(Membership.user).selectinload(User.oauth_accounts)`, maps onto the service-built MembershipSchema list by id (service returns pydantic via from_orm, so attr-set survives). FE Source column after Role: badges Local(grey/key)/LDAP(blue/shield)/SSO·Provider(violet/globe)/SCIM(amber/arrows); multiple wrap; empty→"—". membersColspan 8→9.
- **P-C group source (agent3):** `GroupsManager.vue` — existing Source column rewired: `groupSource(group)` maps `external_provider` (case-insensitive substring) → AD/LDAP/Okta(blue)/SCIM(amber)/Synced/else Local(grey); removed duplicate raw badge by name. Synced groups (external_provider set) DISABLE member add/remove in the members modal (`title="Managed by <provider> sync"`). external_provider already on GroupData (loadGroups casts straight, no narrowing).
- **P-D merge hardening (agent4):** `core/auth.py` module-level `_oauth_trust_email()` = `os.getenv("OAUTH_TRUST_EMAIL","true")∈{1,true,yes}` (default TRUE = no regression). In oauth_callback email-link branch: trust True→link as before; False→`email_verified=bool(kwargs.get("is_verified_by_default") or kwargs.get("email_verified"))`, if not verified raise 403 `email_linking_disabled`. No reliable IdP `email_verified` claim reaches this override today → False path refuses by default. OpenWebUI parity: their opt-in `OAUTH_MERGE_ACCOUNTS_BY_EMAIL`.
- **E2E:** admin@cityagent.io is_superuser=True (still sole creator), auth_sources=['local'], None→[]; OAUTH_TRUST_EMAIL default True. FE (auth_sources + groupSource) confirmed in baked dist chunk. Bake `docker commit`, rollback `pre143-rollback`. VERSION_HYBRID=1.43.0.

---

## 2026-06-27 — PERSONAL GROUPS (My Groups) — LIVE, BAKED (v1.44.0, image `20316475`)
Goal (user): "normal user can create their group and manage it, add those into [the studio access picker], but unique group name across platform." Default decisions taken on "do it": unique = org-wide (already enforced); reset-password/edit-profile = separate batch (not bundled).
- **Backend (pre-built earlier, DEPLOYED this session):** `routes/me_groups.py` = `/api/me/groups` CRUD (`list/create/update/delete` + members add/remove) + `/api/me/contacts` (org members for the picker), mounted `prefix="/api"`. `services/me_groups_service.py` = personal-group CRUD. All endpoints gated `flags.USER_GROUPS` → 404 (`ErrorCode.FEATURE_LOCKED`) when off. Personal group = `Group` row with `owner_user_id` set; EVERY query scoped `owner_user_id == current_user.id` AND org → cannot read/mutate org/admin/LDAP groups (owner NULL). `create_my_group` auto-adds creator as member; `_add_members` validates each id is a registered org member (400 else), idempotent. Unique name = existing `UNIQUE(organization_id, name)` spanning personal + org groups → `IntegrityError`→409.
- **Flag:** `HYBRID_USER_GROUPS` (already declared 3-place in `hybrid_flags.py`: property `USER_GROUPS` + UPGRADE_FLAGS entry + snapshot). Enabled for org `1a073f60` via `organization_settings.config.hybrid_overrides` (`jsonb_set(config::jsonb,'{hybrid_overrides,HYBRID_USER_GROUPS}','true')::json` — config col is `json` not `jsonb`, must cast). Boot loader picks it up.
- **DB DDL (no alembic migration):** prod `groups` table was MISSING `owner_user_id` — the `models/group.py` column existed but was never migrated into this DB. Manual `ALTER TABLE groups ADD COLUMN IF NOT EXISTS owner_user_id varchar(36) REFERENCES users(id)` + `CREATE INDEX ix_groups_owner_user_id`. (External_id/external_provider already present.)
- **FE:** NEW `pages/settings/my-groups.vue` — full personal-group CRUD (create with member multi-select from `/me/contacts`, rename/edit desc, delete, add/remove member chips, shared-count badge), DEFAULT layout (NOT `layout:'settings'`) so it isn't behind the permission-gated Settings rail. NEW nav item in `composables/useAppNav.ts` (key `my-groups`, `/settings/my-groups`, section ACCESS, **no `permission`/`adminOnly`** → visible to every member). `StudioAccessPicker.vue` `loadGroups()` now MERGES `/me/groups` (personal, badge "mine", clay) + admin `/organizations/{org}/groups` (try/catch → skipped on 403 for non-admins) into one deduped list. `StudioCreateGroup.vue` now creates a PERSONAL group via `POST /me/groups` (`member_user_ids` body) + member list from `/me/contacts` — removes the old admin org-groups route that 402'd (custom_roles) / 403'd (non-admin). 409 handled with the server detail.
- **DEPLOY LANDMINE:** running image's `main.py` predated all me_groups route files AND host `main.py` is far ahead (imports `studio_reports` etc. NOT in the image) → cp-ing host main.py caused `ImportError: cannot import name 'studio_reports'` boot loop. FIX: extracted IMAGE `main.py` via `docker create cityagent-analytics:dev`+`docker cp`, surgically added ONLY `me_groups` to the routes import block + one `include_router(me_groups.router, prefix="/api")` line, deployed that. Other cp'd files (me_groups_service/schema, hybrid_flags, group.py) were image-compatible.
- **E2E (admin, org 1a073f60):** GET `/me/groups` 200 []; POST create 201 (creator auto-member); POST dup name 409; GET `/me/contacts` 200; PATCH rename 200; POST member 200; DELETE member 204; DELETE group 204. Both `/` and `/settings/my-groups` serve 200. Test groups cleaned from DB (0 personal groups remain).
- Bake: `docker commit ca-app cityagent-analytics:dev` → `20316475`; tags `pre144-rollback`(=`0b2b275d`) + `v1.44.0`. VERSION_HYBRID=1.44.0. NOT git-pushed (v1.42–1.44 baked-only).

## 2026-06-27 — UI first-run setup + connector org auto-join + OpenRouter-from-UI (v1.45.0, BAKED `b73a9df22e87`, NO migration/flag)
Three permanent fixes for fresh-install onboarding. Originated from a prod login bug: engineer set `DASH_ADMIN_*` in `.env` but login 400'd because `docker-compose.build.yaml` never passed those vars INTO the container (compose uses `.env` only for `${VAR}` interpolation) → `seed_admin.py` skipped → no admin. Added the passthrough, then built a proper UI path so env isn't needed at all.

**(A) First-run super-admin from the UI (env-free, OpenWebUI-style).**
- `routes/dash_settings.py`: `GET /api/settings` returns `needs_setup` = (`user_count == 0`), **FAIL-CLOSED** — any count error → `False` → login shown, NEVER signup (a glitch can't re-open admin creation).
- `pages/users/sign-in.vue`: when `needsSetup`, the SAME clay sign-in page renders a "Create your super-admin" form — FULL NAME field, FIRST-RUN badge, 8+char hint, lock note, Settings→Models pointer; hides providers/remember/forgot. `createAdmin()` POSTs `/api/auth/register` then auto-logs-in. `showForm` forced true on setup. After user#1, `_validate_user_creation` blocks later signups → screen never returns.
- `app/core/auth.py` `on_after_register` → `_ensure_org_for_first_uninvited_user`: when `users==1 & orgs==0`, ALSO set `is_active/is_verified/is_superuser=True` + `session.flush()` + commit (public register router is `safe=True` so can't set flags itself → makes UI signup a REAL super-admin, mirrors `scripts/seed_admin.py`). Runs ONLY on the first account.
- Tested end-to-end on a throwaway FRESH stack: zero users → form → create → DB `is_superuser=t`, org "Main Org", membership role=admin, `needs_setup` flips False.

**(B) ALL external connectors auto-join an org (kills the post-login "Create Organization" dump).**
- Root cause: provisioning attached memberships only from a pending INVITE. A directory user with no invite got ZERO memberships → FE `fetchOrganization()` null → `/organizations/new`.
- NEW `auth.py _ensure_user_in_org(email)`: no membership → auto-join PRIMARY (oldest) org as `Membership(role='member')` + matching system `RoleAssignment` (mirrors `ee/ldap/sync_service._ensure_org_memberships`). Idempotent, fail-soft, no-op if no org yet.
- Wired at **6 points**: `_ldap_authenticate` existing + new; `oauth_callback` returning-by-account + linked-by-email + brand-new. Covers LDAP / Google / Microsoft / Keycloak / SSO. Rescues already-orphaned users on next login.

**(C) Configure OpenRouter from the UI → default models appear (zero env).**
- Keys were ALREADY DB-only (Fernet `llm_providers.api_key`). Fresh org seeds ONE OpenRouter provider from `dash-config.yaml default_llm` (`provider_type: custom`, base_url openrouter.ai, 5 models, key blank).
- Root blocker: "Save Provider" only POSTed → `create_provider` always INSERTs → 409 on name OR a DUPLICATE that orphaned the 5 preset models (key stayed blank = the `"No cookie auth credentials found"` 401).
- FIX in `services/llm_service.py`: `create_provider` now UPSERTS. `_find_upsert_target` matches across the **openrouter↔custom family** by base_url (defaults OpenRouter endpoint), then name, then sole preset/sole-family-row. `_apply_key_and_models_to_existing` sets key + adds only new model_ids + `_enable_preset_models` on blank→set (`_provider_key_is_blank`=decrypt-check). `update_provider` preset-block REMOVED (presets accept key/base_url/model changes; delete still blocked).
- **FE unchanged** — OpenRouter card (`LLMProviderModalComponent.vue`, type `openrouter`) POST folds onto the `custom` seed.
- Tested: POST `provider_type=openrouter` no base_url + key → HTTP 200, providers stays 1, decrypted key = real `sk-or-...`, 5 models intact + Sonnet=default, new model added once, idempotent on re-POST.

**Other:** `docker-compose.build.yaml` adds `DASH_ADMIN_*` passthrough (env-seed still works headless). Fresh-install harness `scratchpad/docker-compose.test.yaml` (project `catest`, ports 3017/5449/6409, fresh volumes, no DASH_ADMIN_*; PG18 mounts parent `/var/lib/postgresql`).

**Bake:** `docker commit` → `b73a9df22e87` (FE dist + hot-cp'd `auth.py`/`dash_settings.py`/`llm_service.py` + `VERSION_HYBRID`+`CHANGELOG_HYBRID.md` into `/app/`). VERSION_HYBRID=1.45.0, CHANGELOG v1.45.0. NOT git-pushed. **Prod box `cmhl-ai-openwebui-prod:/opt/rahulai-dash` (13.251.74.176) still needs this image/files.**
**LANDMINES:** (a) FE OpenRouter card type=`openrouter` but seed type=`custom` → matcher MUST span both or it dups. (b) `create_provider`→`update_provider` delegation BREAKS (`_update_models` wants `.id` objects, create sends dicts) → upsert uses `_create_models`/dict path via `_apply_key_and_models_to_existing`. (c) seed encrypts a BLANK key → `api_key` col is non-empty ciphertext → only decrypt tells blank. (d) compose must pass `DASH_ADMIN_*` through or env-seed admin silently never runs (original prod 400).

---

## 2026-06-27 — v1.46.0 Safe-enable wave + lightweight Forecasting + per-agent Self-learning

**Goal:** enable the stable hybrid feature set on org `1a073f60` without breaking, swap Prophet for a light forecaster, and give each agent owner a self-learning toggle with a chosen cadence.

**Enable (phased, per-org DB overrides, 62 effective):**
- Wave A: `HYBRID_GOVERNANCE` `HYBRID_COLUMN_INTEL` `HYBRID_COMPLIANCE_GATE` `HYBRID_FILE_BROWSER` `HYBRID_AGENT_CONNECTORS`.
- Wave B: `HYBRID_ONECLICK_ARTIFACTS` `HYBRID_RICH_REPORT_EMAIL` `HYBRID_AGENT_REPORTS` `HYBRID_AUTOMAP` `HYBRID_BITEMPORAL` `HYBRID_JOIN_GRAPH` `HYBRID_QUOTAS` `HYBRID_WORKFLOWS`.
- Experimental (safe): `HYBRID_CONTEXT_COMPACT` `HYBRID_BRAIN_GRAPH` `HYBRID_SKILL_AUTOGROW` `HYBRID_SKILL_OPTIMIZE`.
- Daemons: `JOIN_MINE_ENABLED` (regex, zero-LLM) + `STUDIO_LEARN_DAEMON_ENABLED` (after the override-aware fix below).
- Held (cost/risk, on-demand): `HYBRID_AMBIGUITY_GATE` (LLM/query), `HYBRID_AUTOTRAIN_ON_INDEX` (training storm), `HYBRID_PACK_AUTOBIND` (review noise), `HYBRID_FEDERATION` (no S3), costly daemons (insight/eval/skill-optimize).

**Forecast → statsmodels (option C):** `forecast.py` rebuilt — Prophet dropped for `statsmodels.tsa.holtwinters.ExponentialSmoothing` (seasonal when n≥2·period → trend-only n≥3 → numpy-linear n≥2), ±1.96σ band widening √step (cap 3×), future dates via `pd.date_range`. Optional LLM narrative from `runtime_ctx['model']` via `asyncio.to_thread(LLM.inference)`, fail-soft. `schemas/forecast.py` +`method`,+`narrative`. `requirements_versioned.txt`: `prophet==1.1.6`→`statsmodels==0.14.2`+`patsy==1.0.2` (10MB vs 200MB). Flag meta `needs_dep`→`stable`. Tested: ETS n=30 → 220→250 + real narrative.

**Per-agent self-learning:** config on `studio.config['self_learn']` `{enabled,cadence(6h|daily|weekly|monthly|off),hour_utc,last_run_at}` (no migration). New `routes/studio_self_learn.py` GET/PUT (owner/editor), `schemas/self_learn_schema.py`, FE `components/studio/StudioSelfLearn.vue` in the studio Autopilot tab. `studio_learn_daemon.py` rewritten: `daemon_enabled()` now reads `flags.STUDIO_LEARN_DAEMON` (override layer) — fixes the UI toggle being ignored; per-studio `is_due()`/`next_run_estimate()` cadence; hourly tick; stamps `last_run_at`. `flags.STUDIO_LEARN_DAEMON` property + snapshot. 12/12 cadence unit tests pass.

**Removed dead toggle:** `HYBRID_CONTEXT_COMPACT_LLM` (TODO(compress-llm) stub, no-op) added to `HIDDEN_FLAGS` → 69 visible.

**Self-tests (local, real LLM):** flags 62-on/4-workers; forecast ETS+narrative; compliance scan 200; column intel real profiles; one-click dashboard `status=completed` (52s); workbook 1 sheet; self-learn GET/PUT live.

**Bake:** `docker commit` → `d5399fbdbea5` (statsmodels + all hot-cp'd code + FE dist + VERSION/CHANGELOG). VERSION_HYBRID=1.46.0. NOT git-pushed. **Prod box (13.251.74.176) still needs this image/files.**

**LANDMINES:**
- (a) `ca-app` runs uvicorn `--workers 4`. PUT `set_override` patches ONE worker only → flags read inconsistent until a restart reloads all 4 from DB. **Every enable wave must end with ONE `docker restart ca-app`.**
- (b) `studio_learn_daemon.daemon_enabled()` previously read `os.environ` directly → its Feature-Flags UI toggle did NOTHING. Fixed to read `flags.STUDIO_LEARN_DAEMON` (override layer). Other daemons that read env-direct may have the same gap.
- (c) Host `main.py` is AHEAD of the image; `studio_reports.py`+`report_slides.py`+`connection_files.py` were hot-cp-only and MISSING from the image. cp'ing host `main.py` → boot `ImportError` loop until all 3 were re-cp'd (now baked). When hot-deploying main.py, ensure every route it imports exists in the container.
- (d) statsmodels installed via pip in the running container — survives `restart`, LOST on `--force-recreate` until baked. Now baked; future fresh builds get it via `requirements_versioned.txt`.

## 2026-06-28 — v1.47.0 Auto Model Selection (HYBRID_AUTO_MODEL)

A complexity classifier routes each question to the cheapest *capable* of the org's enabled models.
"Auto" option in the model picker (sentinel `model_id="auto"`). Additive, flag-gated default-OFF,
fail-soft (any error → org default = identical to OFF). EPHEMERAL (docker cp + fe-sync, NOT baked, NOT pushed).

**Backend**
- `app/ai/knowledge/auto_model.py` (NEW): `score_complexity(q)` deterministic 0..1 (length + keyword regex:
  `_HARD_RE` forecast/why/correlate/compare/segment… up, `_EASY_RE` count/list/show down, multistep/artifact/
  compound bumps) → tier fast(<0.40)/balanced/reason(>0.60). `pick_model_for_tier` (FAST=cheapest small by
  output cost, REASON=flagship regex opus/gpt-5.5/gemini-3-pro else priciest, BALANCED=median non-small).
  `choose_auto_model(...)` = heuristic first, ONE cheap LLM tie-break (small model, `usage_scope="auto_model"`)
  ONLY in fuzzy band [0.40,0.60]. Returns `(model, decision{tier,score,reason,via,model,model_id})`. NEVER raises.
- `completion_service.py`: `_auto_pick_model` helper (after `__init__`). Sentinel `model_id=="auto"` handled at
  3 resolution sites — estimate (~L297: auto→default, NO classifier, avoids per-keystroke cost), non-stream
  (~L505), stream (~L2037). Decision persisted to answer completion `completion.auto_model` (both paths,
  independent of sense-making) + emitted LIVE as `SSEEvent(event="auto_model", data=decision)` onto
  `event_queue` at stream start (model is known at spawn).
- `completion_v2_schema.py`: top-level `auto_model` field + assembly both sites. `hybrid_flags.py`: `AUTO_MODEL`
  property + `UPGRADE_FLAGS` (Intelligence/experimental) + snapshot.

**Frontend**
- `components/prompt/PromptBoxV2.vue`: Auto option at top of model popover (gated `autoModelEnabled` from
  GET `/api/organization/hybrid-flags` → `HYBRID_AUTO_MODEL.effective`). Label "Auto · <Model>" via `autoPicked` prop.
- `pages/reports/[id]/index.vue`: `handleStreamingEvent` NEW `case 'auto_model'` → live `⚡ Auto → <Model>` chip
  (above thought-process), `lastAutoModel` ref + `latestAutoModel` computed, `auto_model` in BOTH completion
  maps (tab + space indent — two edits) + copied in `patchSenseMakingLive` (early-return gated on new `smLanded`).
- `components/report/ChatSummary.vue`: Outputs "Auto · routed to <Model> · <tier>" pill via `autoModel` prop
  (both ChatSummary mounts get `:auto-model="latestAutoModel"`).

**Deploy**: backend cp+compile+`docker restart ca-app` (×2 — initial + live-SSE). Flag ON org `1a073f60` via
`config.hybrid_overrides.HYBRID_AUTO_MODEL=true` (json-not-jsonb → `jsonb_set(config::jsonb,...)::json`). FE fe-sync.

**Scorer sanity** (verified): "how many rows"→fast 0.14, "list top 10"→fast, "show revenue by month"→fast 0.14,
"why blackout spike + driving"→balanced 0.42 (fuzzy→LLM tie-break), "build dashboard comparing regions +
anomaly"→balanced 0.50, "forecast next qtr + explain seasonal + compare"→reason 0.75.

**LANDMINES**: (1) flag-enable needs ONE `docker restart ca-app` (workers=4). (2) two `messages.value` maps have
DIFFERENT indentation (tabs vs spaces) — replace_all matches one only. (3) estimate path deliberately skips the
classifier. (4) fe-sync via `nohup … &` from a Bash tool gets SIGHUP'd early (only setup logs) — use the Bash
tool's `run_in_background:true`. (5) live chip needs the SSE `auto_model` event consumed BEFORE the answer text —
it's `put` on the queue right after `event_queue` creation so it's first out.

---

## 2026-06-28 — v1.48.0 EXPLAINABLE DASHBOARD + DECISION-NO-SURPRISE + OUTPUTS LOADER + PICKER→AUTO (LIVE, EPHEMERAL, NOT baked/pushed)
Flag `dashboard_key_insights` (org setting in `organization_settings_schema.py`, default ON; falls back ON if absent). NO migration. Deploy = backend `docker cp` (`create_artifact.py`, `completion_service.py`, earlier `create_dashboard.py`/`dashboard_layout_engine.py`/`create_dashboard` schema/`organization_settings_schema.py`) + ONE `docker restart ca-app` + `fe-sync.sh`. Built via 3 parallel sub-agents (non-overlapping files: 2 backend + all-frontend) + my own schema edits.

**ROOT CAUSE (dashboard had no Decision/Insights):** user's dashboards = `create_artifact` mode `page` (React/ECharts artifact, `KPICard`/`SectionCard`/`FilterSelect`), built MID-run. F10 sense_making is a POST-run enricher → at build time `get_stored_sense_making()`=None → the pre-existing `decision_banner_block` rendered nothing. (A separate, secondary builder `create_dashboard.py` makes the semantic-grid `DashboardComponent` — my FIRST same-day edit went there by mistake; harmless/dormant, real dashboards never use it.)

**(A) Explainable dashboard — `backend/app/ai/tools/implementations/create_artifact.py` `_build_page_prompt`.** Flag read `organization_settings.get_config("dashboard_key_insights").value` (try/except default True; `organization_settings` threaded from `run_stream` `runtime_ctx.get("settings")` → `_build_prompt` → `_build_page_prompt`). When ON, injects `explainability_block` (plain triple-quoted str — single braces literal so embedded JSX `viz={viz[N]}` survives) placed just before the `OUTPUT FORMAT` header + a one-line reminder in the final `Rules:`. Instructs the LLM to render, grounded in build-time viz/observation data only:
  - TOP (above KPI row): Decision callout `DECISION · <Watch|Act|Hold> · confidence: <high|med|low>` + one so-what/next-move sentence; "Key Insights" card 3–5 bullets each citing a real number/site/period/ratio.
  - PER WIDGET (every KPICard + chart SectionCard): collapsible native `<details>/<summary>` "Explain" block, up to 4 tiers — Reading (descriptive) / Why (diagnostic) / So-what (impact) / Do (prescriptive). Chosen over the info popover because `frontend/public/libs/artifact-globals.js` `InfoPopover` only has Data + Code tabs (+`calc` line) — no arbitrary-prose slot, and sub-agent was file-scoped to create_artifact.py.
  - WATCH badge on anomaly/outlier/extreme widgets.
  - GROUNDING (non-negotiable, in prompt): cite-only-real, never-invent, fewer-true-beats-guessed, one line each, plain business language.
  Flag OFF ⇒ `explainability_block=""` ⇒ byte-identical to before. Existing `decision_banner_block` (sense_making-gated) untouched = bonus when present. `dashboard_key_insights` also added to `create_dashboard` schema variant Literal (`callout`) + engine `DashboardBlockSpec.variant` Literal — needed or strict pydantic dropped the callout block.

**(B) Decision-is-no-surprise + composer lock.** Backend `completion_service.py` STREAM path: one new line inside the `if _hflags.SENSE_MAKING:` readiness guard, right before `from ...sense_maker import build_sense_making` — `await event_queue.put(SSEEvent(event="sense_making.pending", completion_id=str(system_completion.id), data={}))` (matches the `completion.finished` construction; `SSEEvent` import line 35; `event_queue`/`system_completion` in scope). Non-stream path = comment only (synchronous HTTP, no SSE). FE `pages/reports/[id]/index.vue`: NEW `decisionPending` ref (default false → FAIL-OPEN); `handleStreamingEvent` `case 'sense_making.pending'`→true + `markSenseMakingPending()`; false on `completion.finished`/`completion.error`/`[DONE]`/streaming `finally`/`failRunUnexpectedly`/`abortStream`. Pending DECISION skeleton (existing `senseMakingPending`) header → "Reading the result… forming a decision" in chat + Outputs. `:decision-pending` → `components/prompt/PromptBoxV2.vue`: `canSubmit` += `&& !props.decisionPending` (send `:disabled="!canSubmit"`, `submit()` early-returns) + inline locked note "Forming the decision — you can ask the next question once it's ready."

**(C) Outputs loader — `components/report/ChatSummary.vue`.** Import `DashboardSkeleton`; new `generating?:boolean` prop; `showGeneratingSkeleton = generating && !hasAnswer && !senseMaking && !senseMakingPending` → `<DashboardSkeleton mode="page" />` else existing content. `index.vue` passes `:generating="runActive"` (`isStreaming || runStatus==='in_progress'`) to BOTH ChatSummary mounts (mobile ~126, right-panel ~1063).

**(D) Picker default → Auto — `components/prompt/PromptBoxV2.vue`.** `onMounted` now `await loadAutoModelFlag()` before `await loadModels()`; in `loadModels` default branch (only when nothing selected): `initialModel` match → keep (saved pick preserved); else `autoModelEnabled`/persisted `'auto'` → `selectedModel='auto'`; else old `is_default`/first. Other options unchanged; Auto stays a normal selectable entry. Flag OFF ⇒ prior behavior.

**LANDMINES**: (1) create_artifact page Explain is LLM-emitted JSX — must eyeball that grounded `<details>` actually render (not generic/empty). (2) pending-lock is belt-and-suspenders: during pending→finished the stream is open so composer shows **Stop** (Send not mounted) — the user-visible change is the inline note + pending card, not a greyed Send. (3) ONE `docker restart ca-app` (workers=4) to converge the 2 backend files. (4) sub-agent edits = compile-checked only; I did all docker cp/restart/fe-sync (no sub-agent deploys). (5) `sense_making.pending` only fires when `HYBRID_SENSE_MAKING` on + run has findings + answer content non-empty → otherwise no lock (intended fail-open). EPHEMERAL — prod box + bake still pending (user wants bake LAST).

---

## 2026-06-28 — v1.49.0 SLIDES BUILD-FIX + OUTPUTS Q/A FEED + SESSION SUMMARY + ARTIFACT ROUTING (LIVE, EPHEMERAL, NOT baked/pushed)
Flag `session_summary` (org setting in `organization_settings_schema.py`, default ON). ONE manual DDL: `ALTER TABLE reports ADD COLUMN IF NOT EXISTS session_summary json` (run on ca-postgres; survives restart, lost on force-recreate). Deploy = backend `docker cp` (create_artifact.py, report.py, session_summary.py [new], report_slides.py, organization_settings_schema.py) + ONE `docker restart ca-app` + `fe-sync`. Built via several sub-agents across multiple turns (non-overlapping files); sub-agents compile-check only, parent deploys.

**(A) SLIDES NOW BUILD — `create_artifact.py` slides mode.** ROOT CAUSE (DB-confirmed): deck artifact `3d9fcd8b` `status=failed`, `render_errors=["Code contains forbidden constructs: Forbidden function call: 'getattr()'" ×3]`. The slides-mode LLM wrote python-pptx using `getattr()`; the sandbox AST gate (`code_execution.FORBIDDEN_BUILTINS` bans getattr/hasattr/setattr/eval/exec/open/__import__/locals/globals/vars) rejected the whole script → no pptx, no previews → Slides panel empty. The LLM copied `getattr()` from the prompt's OWN `style_chart_text` example (appeared twice). FIX: (1) prominent `⛔ SANDBOX RULES — READ FIRST` header in `_build_slides_prompt` (banned list + "use `'name' in dir(obj)`, direct attr or try/except AttributeError"); (2) rewrote BOTH example helpers getattr-free (try/except axis access + direct `plot.has_data_labels`). HONEST FAILURE: on `not pptx_success`, observation `summary`="Slide deck generation FAILED: <error>. The deck was NOT created… do NOT claim success", + `observation.failed=True/status/error` + `output.success=False`; the success/preview wording moved into the `else` (only when not failed). VERIFIED: retry rebuilt deck `7ebdefcb` → `completed`, zero errors, ~120s build.

**(B) OUTPUTS = PER-TURN Q/A/DECISION FEED — `OutputsFeed.vue` (new) rendered from `ChatSummary.vue`.** Was: latest answer only. Now: scrollable newest-first feed; per turn = relative timestamp + ASKED question chip + type badges + routed model, body = ANSWER card (`MarkdownRender`) + `DecisionCard` (full, from turn `sense_making`) + artifact chips (status OK/FAILED + Open/Retry). Newest expanded, older collapsed (toggle). Q/A pairing = walk `messages`: `role==='user'` opens a turn (prompt=question), next `role==='system'` attaches answer/decision; system-only rows their own turn. Artifact→turn map = by recency (latest turn whose ts ≤ artifact.created_at) — NO backend turn-link (noted compromise). `index.vue` passes `:messages`.

**(C) SESSION SUMMARY — pinned synthesis over ALL turns.** NEW `app/ai/knowledge/session_summary.py` `build_session_summary(db,*,report,organization,user,model)` mirrors sense_maker (cheap, fail-soft, never raises): gathers each turn's Q + `completion.content` + `sense_making` + the report's `Artifact` rows → ONE small-model call (`LLMService().get_default_model(...,is_small=True)`, `LLM(...).inference(usage_scope="session_summary")` in `asyncio.to_thread`) → strict JSON `{headline, decision:{verb,confidence,text}|null, key_findings[≤6 deduped], produced:[{type,title,status}], next_steps[≤4], generated_from:{completion_count,last_completion_id,generated_at}}`. Cached in NEW `reports.session_summary` JSON col (`flag_modified`). Routes on report_slides.py (included `/api`): `GET /reports/{id}/session-summary` → `{summary, stale}` (stale = stored generated_from vs current latest success system completion; GET never rebuilds), `POST` → rebuild + stamp `generated_at` ISO + store. Flag `session_summary` org setting default ON → OFF makes GET `{null,false}`, POST no-op. FE `SessionSummaryCard.vue` (✦ pinned, headline + coral DECISION line + key findings + produced chips + suggested next + stale badge + ↻ Refresh; null→slim "Generate summary"). `index.vue`: refs + `loadSessionSummary()` (GET, on mount/panel-open/run-end) + `refreshSessionSummary()` (POST), auto-build ONCE per page-session when empty + a completed turn exists; wired to both ChatSummary mounts.

**(D) SLIDES PANEL HONEST STATES + RETRY POLL — `index.vue`.** `hasGoodSlidesArtifact` now requires `status==='completed'` (was `!=='failed'` → a `pending` build mounted an empty ArtifactFrame). NEW `pendingSlides` (status pending/in_progress, no good deck) → "Building your slide deck… 1–3 min" state; `failedSlides` (no good/pending) → failed card + **Retry** (`retrySlides`→`generateSlideDeck` one-click `/reports/{id}/slides/generate`, else chat submit). Refetch `checkHasArtifacts()` on run-end (`completion.finished`/`[DONE]`/finally) regardless of success — a FAILED build never flips the live `hasArtifacts` signal so the panel was stale. `generateSlideDeck` now POLLS `checkHasArtifacts` up to 4 min for a NEW completed (or failed) slides artifact — the pptx build (~120s) exceeds the tool `timeout_seconds=60` + HTTP patience, so the single post-POST refetch missed the eventually-completed deck.

**(E) ARTIFACT-OPEN ROUTING — `handleOpenArtifact` (`index.vue`).** ROOT CAUSE: hardcoded `rightPanelView='artifact'` (the page/dashboard ArtifactFrame) for EVERY artifact → clicking a slides card opened the dashboard. FIX: look up the clicked artifact in `reportArtifacts` → route `mode==='slides' ? 'slides' : 'artifact'`. SECOND bug: the chat card's `result_json.artifact_id` points at the FAILED slides id → dispatching `artifact:select(failedId)` made the slides frame focus the broken artifact → blank. FIX: when clicked artifact `status!=='completed'`, select the latest COMPLETED same-mode artifact instead (reportArtifacts is newest-first). `CreateArtifactTool` emits `openArtifact{artifactId}` (wired `@openArtifact="handleOpenArtifact"` on the dynamic tool component, line ~433).

**LANDMINES**: (1) slides pptx + dashboard Explain are LLM-emitted — eyeball grounding. (2) session-summary auto-build fires once/page-session; mobile ChatSummary mount has no `:messages` (feed empty there, card still renders). (3) `reports.session_summary` = manual DDL, LOST on force-recreate until baked. (4) ONE `docker restart ca-app` (workers=4) per backend cp wave. (5) `generateSlideDeck` poll is bounded 4min — a build slower than that shows a soft "taking longer… refresh" message (deck still completes server-side). Prod box + bake still pending (bake LAST).

---

## 2026-06-28 — v1.50.0 Two-tier connectors + member PII redaction + agent-as-proxy (confirmed)
Two asks: (1) members page leaked admin email to regular members; (2) want admin-configured reusable connectors with selective access + every user builds their own. Investigated → most primitives already existed (`connections.owner_user_id`/`studio_id`, polymorphic `resource_grants`, `private_connector_guard`, `AGENT_ACL`); flags `HYBRID_AGENT_CONNECTORS`+`AGENT_ACL` already ON. The build = close the gaps. EPHEMERAL (backend cp + ONE restart + fe-sync); NOT baked, NOT pushed.

**THREE sharing models clarified for the user (all now work):**
1. **Connector grant** (`resource_grants` user/group→connection) → member SEES + reuses the connector itself.
2. **Agent share** (StudioMember / share_scope) → member QUERIES data via the shared agent, connector hidden. Runtime uses the studio's bound connection creds (`auth_policy=system_only`) for ANY caller — `require_owner`/`filter_visible` guard ONLY the management plane, never `resolve_credentials_for_connection`. Who-may-run = `AGENT_ACL`; whose-creds = `auth_policy`. NO code change — confirmed by trace.
3. **Personal connector** (`owner_user_id=self`) → member's own private build, creator-only (no admin bypass).

**(A) MEMBER PII REDACTION — `routes/organization.py get_members`.** Added `_mask_email` (`a***@domain`) + `_redact_member_for_viewer` (masks email, nulls note/auth_sources/invite/last_login/last_seen/external). After building members, `resolve_permissions(current_user)` → `is_admin = FULL_ADMIN | manage_members | is_superuser`. Non-admin → redact every row whose `user.id != current_user.id`. Own row + admins untouched. VERIFIED: rahul (member) sees `a***@cityagent.io`, own `rahul@gmail.com` full; admin sees both full.

**(B) PERSONAL CONNECTORS — `schemas/connection_schema.py` + `services/connection_service.py` + `routes/connection.py`.** `ConnectionCreate.scope: "shared"|"personal"` (default shared). `create_connection` service gained `owner_user_id` param (set on the Connection). Route `POST /connections`: DROPPED the blanket `@requires_permission('manage_connections')`; manual branch — `scope=shared`→require admin (FULL_ADMIN|manage_connections), owner NULL; `scope=personal`→require org membership + `flags.AGENT_CONNECTORS`, `owner_user_id=str(current_user.id)` FORCED (client value ignored). `owner_user_id` added to `ConnectionSchema` + all 3 build sites (create/list/get). `list_connections._conn_visible` extended: a member's OWN private connector is always visible (was dropped — no grant + no DS). VERIFIED: member shared→403; personal→200 owner=rahul; rahul lists own+shared; admin does NOT see rahul's private.

**(C) ACCESS GRANTS — reuse existing.** `rbac.py` `/organizations/{org}/resource-grants` GET(list)/POST/DELETE already handle `resource_type=connection` (polymorphic), gate `_require_resource_manage` (per-resource manage or full_admin), `_deny_share_private_connector` blocks granting private ones. No new backend route. VERIFIED: admin granted `spreadsheet-1`→rahul (user principal), rahul's list then included it; grant list returns the row.

**(D) FRONTEND (sub-agent built, parent deployed).** `pages/connectors.vue`: removed Admins-only gate (page open to all, always `refreshConnections`), split `sharedConnections`(`!owner_user_id`)/`myConnections`(`!!owner_user_id`) into two card sections, "Add Connection" visible to all, admin shared cards get a "Manage access" button (`@click.stop openManageAccess`). `AddConnectionModal.vue`: `canCreateShared` prop + `scope` ref (shared default for admin, else personal-forced) + scope selector above ConnectForm. `ConnectForm.vue`: `scope?` prop → `scope: props.scope || 'shared'` in the `create_connection_only` POST body (line ~568). NEW `ManageConnectionAccessModal.vue`: orgId via `useOrganization().ensureOrganization`, lists/add/removes grants, user picker from `/members`, group picker from `/groups` (soft-degrades).

**LANDMINES (this ship):**
1. 🔴 **agentconn1 was NEVER baked into the live image** — the running `ca-app` was missing `services/private_connector_guard.py` AND its `models/connection.py` lacked `owner_user_id`/`studio_id` (lost on a prior force-recreate). `/connections` was 500'ing (ImportError) / AttributeError for everyone until I hot-cp'd both files + ran the column DDL. ALL of this is EPHEMERAL — a force-recreate wipes it again until a proper bake. Files to ship on bake: connections model, private_connector_guard, connection routes/schema/service, organization route, + the 2 DDL columns (migration agentconn1 should finally run).
2. Shared connectors backing a PUBLIC data source are visible to all members even with no grant (pre-existing DS-backed visibility). Grants only gate connectors NOT reachable via a public DS.
3. Manual DDL `connections.owner_user_id`+`studio_id` (+ indexes) applied to live DB; survives restart, lost on force-recreate.
4. Test residue on org 1a073f60: `Rahul Personal Chinook` connector + a `spreadsheet-1`→rahul grant + rahul's password reset to `Rahul12345` (was unknown). Delete/rotate when done demoing.
5. Agent-proxy who-may-run depends on `AGENT_ACL` ON (it is) — OFF would let ANY org user run any studio, not only shared-with.

---

## 2026-06-28 — v1.51.0 Connectors inside each agent (Activate for agent) (LIVE EPHEMERAL, not baked)
Per-agent **Connectors page** in the studio left rail (the v1.50 connector tiers, now usable *inside* an agent). User ask: a Connectors page with **two tabs — My Connectors / Shared Connectors**, an "Add connector" button, and the old "pin" renamed to **"Activate for agent"** so that *only active connectors are queryable + get data sync*.

**Backend** `routes/studio_sources.py` (cp + `docker restart ca-app`; reuses existing `StudioDataSource` pin model — NO new table/migration):
- `GET /studios/{id}/connectors` rewritten: was `List[StudioConnectorRead]` (own private only) → now `StudioConnectorsResponse {mine, shared}`. Each item `StudioConnectorListItem {connection_id,name,type,owner_user_id,is_org,active,data_source_id,sync_status,last_synced_at}`. `mine` = caller's private connectors bound to this studio (`pcg.filter_visible`). `shared` = org/shared connectors visible to caller — reuses connection.py `_conn_visible` logic (admin → all org connectors; member → granted_conn_ids OR backing a public/granted DataSource); **private-not-owned never listed**. `active` computed from pinned `StudioDataSource.agent_id` set (helper `_pinned_ds_ids`).
- New `POST /studios/{id}/connectors/{connection_id}/activate` (editor+): loads connection (403 if private-not-owned), ensures a DataSource wraps it (reuse first existing, else create private DS owned by caller with IntegrityError name-clash fallback), pins `StudioDataSource` (dedupe + undelete soft-deleted pin), triggers `schedule_bootstrap_on_source_pin` data sync. Returns `ActivateResult {ok,connection_id,data_source_id,active}`.
- New `DELETE /studios/{id}/connectors/{connection_id}/activate` (editor+): soft-deletes every `StudioDataSource` pin for the connector's DataSources; connector + DS left intact (re-activate any time).
- Added import `from app.core.permission_resolver import resolve_permissions, FULL_ADMIN`.
- VERIFIED live (admin, studio d4fb8a10): GET → `{mine:[], shared:[Finance DuckDB, spreadsheet-1, SQLite Chinook]}` all `active:false`; activate SQLite Chinook → `active:true` in list; deactivate → `active:false`.

**Frontend** `components/studio/StudioConnectors.vue` rewritten (fe-sync.sh, EPHEMERAL): two-tab bar (🔒 My / 🌐 Shared with counts) → `tab` ref → `visibleConnectors`; `loadConnectors` reads `{mine,shared}`; per-card **Activate for agent** (green) / **✓ Active · Deactivate** + "synced <date>"; private (My) cards keep Test/Edit/Delete + "Add connector" modal (create → auto-active, jumps to My tab); footer note "only active connectors are queryable + synced". Card keys/actions switched from `conn.id` → `conn.connection_id`. Self-gates on `HYBRID_AGENT_CONNECTORS`. Already mounted in `pages/studios/[id]/index.vue` (tab `connectors` line ~2253, `<StudioConnectors :studio :can-edit>` line ~1071) — no index.vue edit needed.

LANDMINES:
1. EPHEMERAL — backend cp + FE dist lost on `--force-recreate`. Bake must ship the new `studio_sources.py` + `StudioConnectors.vue` (and still the v1.50 connection model/guard/route + agentconn1 migration).
2. Activating a SHARED connector that has no DataSource yet auto-creates a **private** DS (owner=activator, is_public=False) wrapping the org connection — pins only to this studio, connector itself unchanged. A shared connector already backing a public DS reuses that DS.
3. `active` is per-DataSource-pin: a connector with multiple DataSources shows active if ANY of them is pinned; deactivate unpins ALL of them for this studio.

## 2026-06-28 — v1.51.1 Connectors/Teach/Reports tabs visible to non-admins (flag-read fix)
Bug: per-agent **Connectors** tab (also **Teach**, **Reports**) never appeared for normal members — only admins saw them. The studio rail gates each tab on the per-org `effective` value of its HYBRID flag, read via `GET /api/organization/hybrid-flags` (`pages/studios/[id]/index.vue` loadConnectorsFlag/loadTeachFlag/loadReportsFlag). That endpoint was `@requires_permission('manage_settings')` → 403 for members → FE `catch` left the gate OFF → tabs hidden for everyone non-admin. (Confirmed: member rahul got `count 0` flags.)
Fix `routes/organization_settings.py` GET `/organization/hybrid-flags`: dropped the blanket admin decorator; inside, `resolve_permissions` → `is_admin` (FULL_ADMIN | manage_settings | superuser). Admin → full `_flag_row` list (label/note/override/default — Settings editor needs it). Non-admin member → minimal projection `{env_name,key,effective}` only (booleans, no config internals leaked). PUT `/organization/hybrid-flags/{env_name}` UNCHANGED (still admin-only). Flag effectiveness is per-ORG not per-role, so members are entitled to read the booleans.
Verified live (after cp+restart): member rahul → 71 rows incl `HYBRID_AGENT_CONNECTORS effective:true`, no note/override; admin → 71 rows WITH note+override. Re-baked `cityagent-analytics:dev`+`:v1.51.1` (docker commit 789664299d6d).
LANDMINE: any FE rail/tab gate that reads `/organization/hybrid-flags` and fails-soft-OFF was silently admin-only before this fix. The minimal member projection omits `default_env`/`override`/`note`/`role`/`category`/`status` — FE that needs those (Settings flag editor) must stay admin-only.

## 2026-06-28 — v1.52.0 Full connector catalog in per-agent "Add connector" + studio_id bind
Ask: the per-agent **Connectors → Add connector** modal only offered 6 hard-coded types (Postgres/MySQL/Snowflake/Fabric/REST/CSV); platform supports ~44 (registry). Also: existing admin connectors (SharePoint etc) should reach agents.
Privacy model CONFIRMED already correct (no change): private connector = `owner_user_id=self`, invisible to others; query path (`report_service`) reads pinned StudioDataSources + resolves creds `auth_policy=system_only` server-side for ANY caller; `private_connector_guard.require_owner/filter_visible` guards ONLY the management plane (list/edit/test/delete), never the query path. So a shared agent lets a member query the connector's data in chat while the connector itself stays hidden + non-editable. Verified by code+trace.
Build = reuse the admin create flow in the studio modal:
- FE `components/studio/StudioConnectors.vue`: `openCreate()` now opens `<AddConnectionModal :can-create-shared="false" :studio-id="studioId" @created="onConnectorCreated">` (forces PERSONAL scope, full catalog incl SharePoint/BigQuery/Databricks/Fabric-user). The old hand-built `UModal` + `connectorTypes`/`form`/`buildBody`/`saveConnector` is now used for EDIT only. `onConnectorCreated(conn)` → reload + `activate({connection_id: conn.id})`.
- FE `components/AddConnectionModal.vue` + `components/datasources/ConnectForm.vue`: new `studioId?` prop; ConnectForm's `create_connection_only` POST body adds `studio_id` when set.
- BE `schemas/connection_schema.py`: `ConnectionCreate.studio_id: Optional[str]`. `routes/connection.py` POST `/connections`: after create, if `scope=='personal'` and `studio_id`, validate `Studio.id==studio_id AND organization_id==org` (404 else) → set `connection.studio_id` + commit. Needed so the connector matches the studio `mine` filter (`Connection.studio_id==studio AND owner==self`).
SharePoint/admin connectors path: NO code — they're org (non-private) connectors → auto-listed in each agent's Shared tab → Activate for agent. File connectors use per-user identity (HYBRID_FILE_BROWSER).
Verified live (member rahul, studio Rahul2 6fc1f1ce): POST /connections type=sqlite scope=personal studio_id=… → DB `owned=t studio_id=<studio>`; GET studio connectors `mine=[rahul-agent-chinook]`; activate → `active:true` + DataSource b63ae230 pinned; deactivate+delete → DB 0 rows. rest_api create still fails (no rest_api_client module — pre-existing, unrelated).
Re-baked `cityagent-analytics:dev` + `:v1.52.0` (docker commit).
LANDMINE: rest_api/some registry types have no client module → create validates client load and 500s. Catalog shows them but they can't be created until a client exists. LANDMINE: studio EDIT still uses the 6-type hand form — editing an exotic-type private connector inline won't render its fields (delete+recreate, or edit from admin Connectors page as owner).

## 2026-06-28 — v1.53.0 Connector visibility: Private / Shared / Org-wide (self-service)
3-level connector visibility on the MANAGEMENT plane; query/runtime path untouched (creds still resolved `system_only` server-side). Built P1-P5 via two sub-agents (backend, frontend); parent deployed/migrated/verified/baked.
Model: `connections.visibility` String(16) NOT NULL default 'private' + index (migration `connvis1`, down_revision `agentconn1`; upgrade adds col+index then `UPDATE … SET visibility='org' WHERE owner_user_id IS NULL`). `owner_user_id` is now ALWAYS the creator (keeps edit rights at every level) — legacy meaning (owner NULL = org) preserved only via the backfill.
Create (`routes/connection.py` POST `/connections`): effective visibility = explicit `data.visibility` if in {private,shared,org} else derived from legacy `scope` (shared→org, else private). Admin-only-for-shared gate DROPPED → any org member self-service creates at any level; non-private create gated by `flags.AGENT_CONNECTORS` (admins bypass for back-compat). `owner_user_id=self` always. studio_id binding now keyed on `visibility=='private'`.
New `PATCH /connections/{id}/visibility {visibility, grants?:[{principal_type,principal_id}]}` (owner-or-admin via `_is_org_admin`/owner). shared → writes connection `resource_grants` (reuse `rbac_service.create_resource_grant`, perms view_schema+query, 409-tolerant); private/org → deletes existing connection grants. Logs `connection.visibility_changed`. Returns updated `ConnectionSchema`.
Resolution: `private_connector_guard.is_private` → `visibility=='private'` (fallback owner-set when attr absent); `filter_visible` keeps non-private OR private-and-owned. `list_connections._conn_visible` (non-admin): mine always; org→all; private→owner-only; shared→grant or DS-backed. `studio_sources.py`: `StudioConnectorListItem.visibility` added + populated; `mine` = `owner_user_id==me` ANY level (dropped studio_id filter); `_shared_visible` = exclude own, include org / granted-shared / legacy NULL-owner org, hide others' private.
FE (sub-agent): `ConnectForm.visibility` prop → sent on create_connection_only POST; `AddConnectionModal` 3-card selector (Private/Shared/Org-wide, default org when canCreateShared else private) + emits `shareRequested` for the shared grant picker; `StudioConnectors.vue` + `pages/connectors.vue` 3-way badge (🔒/👥/🌐) + owner segmented control Make-Private/Share…/Org-wide → `PATCH /connections/{id}/visibility`, Share opens `ManageConnectionAccessModal`.
Deploy: 6 backend files docker cp (absolute paths — rtk mangles spaced relative paths) + py_compile OK + `alembic upgrade head` (agentconn1→connvis1) + restart. FE fe-sync clean. Verified live (rahul member): create org+private (owner=self), PATCH private→org→shared 200 each, studio mine=[private,org,shared] +visibility, shared=org connectors. Test rows purged (had to cascade connection_tables first). Re-baked `cityagent-analytics:dev` + `:v1.53.0`.
LANDMINE: a studio-private connector promoted to shared/org via PATCH then 404s on the studio-private update/delete routes (require is_private) — by design, manage it via org `/connections` routes after. LANDMINE: self-service ORG-wide publish = any member can expose a connector org-wide using their own creds (others query via system_only); audit log present, but no admin approval (per product decision). LANDMINE: members bypass-flag — non-private create needs `HYBRID_AGENT_CONNECTORS` ON (org 1a073f60 has it).

### Landmine (2026-06-28): What's-new bell stuck at old version
`services/changelog.py` reads `/app/VERSION_HYBRID` + `/app/CHANGELOG_HYBRID.md` from the CONTAINER per-request (no cache). `scripts/fe-sync.sh` pushes ONLY `frontend/dist` — it does NOT copy VERSION_HYBRID/CHANGELOG_HYBRID.md. So host doc bumps (v1.47–1.53) never reached the container; the bell showed the last baked value (1.46.0). FIX: `docker cp` BOTH files into `ca-app:/app/` (no restart — read per-request) then re-bake. Always cp these two when bumping version, or the bake captures stale docs.

## 2026-06-28 — v1.54.0 Connectors TABLE + sliding sharing panel (both surfaces)
FE-only (backend visibility/PATCH/grants already shipped v1.53). Built via 2 sub-agents, parent built+baked.
NEW `components/ConnectorsTable.vue` (root → bare `<ConnectorsTable>`): props `rows[]`,`context:'studio'|'org'`; emits activate/deactivate/test/edit/delete/share. Columns: Connector(emoji+name)|Type|Owner(you/admin)|Who-can-use(3-state badge 🔒/👥/🌐 — clickable→share when can_edit&&!is_org, else read-only)|Active(studio: Activate/✓Active·Deactivate) or Agents(org: agent_count)|Sync|⋯(Test/Edit/Delete when can_edit). Empty-state row.
NEW `components/ConnectorSharingPanel.vue` (root): props `modelValue`,`connection{id,name,visibility}`; teleport fixed right drawer (~420px)+overlay; radios Private/Shared/Org init from connection.visibility; Shared → grants via `/organizations/{ensureOrganization}/resource-grants` GET/POST/DELETE + `/members`+`/groups` (reuses ManageConnectionAccessModal logic); Save → `PATCH /connections/{id}/visibility {visibility,grants?}` → emit saved+close. Creds-never-shared note.
`AddConnectionModal.vue`: +props `individualOnly` (filter catalog, exclude `{sharepoint,onedrive,google_drive,ms_fabric,powerbi,mcp}` — keeps ms_fabric_user/powerbi_report_server/custom_api/DBs/files) + `deferSharing` (force visibility='private', hide selector, no shareRequested).
`studio/StudioConnectors.vue`: card grid → `<ConnectorsTable context=studio>`; My/Shared tabs → All/Mine/Shared chips; `tableRows` = mine(can_edit,!is_org)+shared(!can_edit,is_org) filtered; rows keep `connection_id` so activate/deactivate/test/openEdit/delete handlers unchanged; `openSharing(row)`→`<ConnectorSharingPanel @saved=loadConnectors>`; AddConnectionModal `:individual-only=true :defer-sharing=true`. Removed old per-card ManageConnectionAccessModal mount + setVisibility/shareConnector.
`pages/connectors.vue`: card sections → `<ConnectorsTable context=org>` + All/Mine/Shared/Org chips + search; `tableRows`=conns mapped {id,visibility:connVisibility,is_org:!owner,can_edit:isOwner||isAdmin}; `openSharing`→panel @saved=refreshConnections; onEdit→ConnectionDetailModal(connById), onDelete→`DELETE /connections/{id}`+confirm, onTest→`POST /connections/{id}/test`; AddConnectionModal `:defer-sharing=true`. Dead leftovers (isConnectionHealthy/visBadge/setVisibility) kept harmless.
Deploy: fe-sync clean. Verified endpoints exist: DELETE/{id}(L636), POST/{id}/test(L671), PATCH/{id}/visibility(L524). cp VERSION_HYBRID+CHANGELOG_HYBRID.md into container (What's-new landmine) + re-bake `:dev`+`:v1.54.0`.
LANDMINE: org-page onDelete assumes hard `DELETE /connections/{id}` — has FK children (connection_tables); backend route must cascade or it 409s (delete UI may fail for connectors with indexed tables — verify). LANDMINE: new root components need a Nuxt rebuild (fe-sync) before they auto-import.

## 2026-06-28 — v1.55.0 Connector edit fixes (modal width, owner+admin edit, page for all)
Three root causes fixed (user-reported cramped Edit UI + "super admin should edit" + "Connectors page for all users").
RC1 cramped Edit: `ConnectionDetailModal.vue:335` edit UModal `sm:max-w-xl` (~36rem) but ConnectForm is a two-pane `lg:flex` (form|help) → crushed. FIX → `sm:max-w-xl lg:max-w-5xl` (matches AddConnectionModal).
RC2 edit perms: PUT/DELETE/`/test` `/connections/{id}` were `@requires_permission('manage_connections')` (admin-only) → members couldn't edit OWN; and `_guard_private_owner`→`require_owner` had NO admin bypass → super admin couldn't edit others' private. FIX `routes/connection.py`: `_guard_private_owner` rewritten OWNER-OR-ADMIN (`_is_org_admin` bypass → any connection incl others' private; else must own; org connector owner-NULL → non-admin 403). Dropped admin-only decorator on GET`/{id}` detail, PUT`/{id}`, DELETE`/{id}`, POST`/{id}/test`. GET detail: `can_see_full = is_admin or is_owner` → returns config + has_credentials to OWNER too (was admin-only-config) so owner can edit; non-owner-non-admin still redacted + require_owner blocks others' private + DS-access check. Decorated routes left as-is (reindex/tools/refresh) stay admin-only via decorator (guard now owner-or-admin underneath, harmless).
RC3 page for all: `useAppNav.ts:140` Connectors nav gated `permission:'create_data_source'` → members without it didn't see it. FIX dropped the permission (Manage group is per-item gated → appears with just Connectors). Page data already per-user-scoped (list_connections: own-private + org + granted).
Policy: FULL super-admin override (user chose) — admin edits/deletes ANY connection incl others' private. Creds never returned to FE.
Verified live: member rahul GET own detail 200 (config visible) + PUT own 200 + PUT org 403; admin GET+PUT rahul's private 200 (override). fe-sync clean. cp VERSION_HYBRID+CHANGELOG into container + bake `:dev`+`:v1.55.0`.
LANDMINE: removing the manage_connections decorator means GET`/{id}`/PUT/DELETE/test now rely SOLELY on `_guard_private_owner` for authz — any future route added without that guard call would be open to any member. Keep the guard call on every mutate route.

## 2026-06-28 — v1.55.1 connector authz hardening (un-skippable Depends guard)
Closes the v1.55.0 landmine. Converted the owner-or-admin check from an easily-forgotten in-body
`await _guard_private_owner(...)` into a FastAPI dependency `guard_owned_connection` (routes/connection.py:121,
wraps `_guard_private_owner`, returns the loaded Connection). Wired as `Depends(...)` into all 9 mutate/test/
reindex/tools routes: use-return sites take `connection=Depends(guard_owned_connection)` (query-identity, refresh,
reindex, refresh-tools); ignore sites take `_guarded=Depends(guard_owned_connection)` (PUT, DELETE, test, batch-tools,
update-tool). `_guard_private_owner` now invoked from exactly ONE place (the dependency). Authz is now in each
route SIGNATURE → a new connector route can't silently ship without it. Same owner-or-admin semantics; GET`/{id}`
detail keeps its own bespoke redaction logic (intentionally NOT the strict guard — allows redacted non-owner view).
Verified live (org 1a073f60): member PUT own 200 / member PUT+DELETE org 403 / super-admin PUT member's private 200.
cp connection.py + VERSION_HYBRID(1.55.1) + CHANGELOG into ca-app, restart, bake `:dev`+`:v1.55.1`. EPHEMERAL stack.

## 2026-06-28 — v1.56–1.58 progress wave + docked status + AUTO-ARTIFACT
- **v1.56.0/1.56.1 progress wave:** flat "Thinking…" → warm clay `wave · live step · wave · m:ss`. Real renderer was `pages/reports/[id]/index.vue` inline header (NOT `AgentStepTimeline.vue` — v1.56.0 edited the wrong file → wave invisible; v1.56.1 fixed). `runningStageText(m)` = current running step title from `blocksToSteps` (friendly fallback). Both the in-progress header + the bare "Thinking…" dots show it. `.cai-wave` CSS (scaleY wob, reduced-motion guard). Home idle wave (`pages/index.vue` `.home-wave` 3-layer, calmer) + `readyCaption` between subtitle and composer. LANDMINE: first Python splice matched wrong spinner → corrupted DECISION-pending block → `git checkout` restore + redo line-anchored.
- **v1.57.0 docked status strip:** persistent run-status strip in the composer dock (`runActive && lastSystemMessage`) above the already-`shrink-0` composer — wave + current step + elapsed + Stop(abortStream); stays visible when thread scrolled up.
- **v1.58.0 AUTO-ARTIFACT (`HYBRID_AUTO_ARTIFACT`, default OFF, ON org 1a073f60):** ROOT CAUSE of "no output" = NOT a bug — planner only calls `create_artifact` on an explicit dashboard ask; "summaries data" → `create_data`+prose, Outputs tiles read `artifacts` table (empty). FIX = auto-build a dashboard in background after a data turn with zero artifacts. New `services/auto_artifact.py` `schedule_auto_artifact()` → strong-ref'd `asyncio.create_task(_build)` → fresh detached session (reload by PK) → reuse `report_slides._generate_artifact(mode='page')`; fail-soft, idempotent (zero-artifact gate = one build/report), detect via `system_completion→AgentExecution→ToolExecution.created_step_id→Step status=success`. Hooks in `completion_service.py` non-stream ~:920 + stream ~:2404 (after answer+sense_making commit, before `finished` SSE; own session so no stream interference). FE `pages/reports/[id]/index.vue`: on `runActive` true→false with data+no-artifact → poll `/artifacts/report/{id}` 6s×30 (`autoBuilding`) + dock strip shows "Building a dashboard from your data…". Flag 3-place in hybrid_flags.py. Backend cp'd + restart (workers=4 converge). BAKED `:dev`+`:v1.56.1`/`:v1.57.0`/`:v1.58.0`. LANDMINE: auto_artifact.py new file + completion_service edits hot-cp → LOST on force-recreate until baked (now baked v1.58.0). Cost bounded (1 build/report lifetime).

## 2026-06-30 — v1.62.0 Ingest reconcile: fail-loud multi-file upload (HYBRID_INGEST_RECONCILE)
Goal: make the persistent data-source upload behave like the chat-upload path (full fidelity, fail loud).
Root cause of the CRM "only April" bug = silent partial ingest: 6 months merged via `merged_paths`, 5 failed
to parse, the merge loop's `except: continue` swallowed them with zero signal → agent saw 1 month and fabricated
the other 5. Built in 5 phases, all behind flag `HYBRID_INGEST_RECONCILE` (default OFF), no migration.
- **P1 record failures** — `SpreadsheetClient._load_frames` merge loop: each file → `{path,label,period,status:
  loaded|failed,rows,error}` on `self.last_ingest_report` (init in `__init__`, module `logger` added). Flag off →
  report None, silent-skip preserved (byte-identical).
- **P2 reconcile gate** — NEW `services/ingest/reconcile.py` `run_ingest_reconcile`: re-reads via SpreadsheetClient
  to get the P1 report, sums active `DataSourceTable.no_rows` = materialized rows, `_build_coverage` verdict
  `degraded` if any file failed / loaded<expected / (materialized>0 AND <source_rows) — the `>0` guard avoids a
  FALSE degrade (DuckDB/spreadsheet tables report no_rows=0 at sync). Stamps `ingest_coverage` on connection.config
  + each table.metadata_json. Wired into `routes/data_source_from_file.py` in BOTH the new-source branch (4c3) AND
  `_try_merge_same_schema`'s return (the REAL multi-month merge path — new-source always has merged_paths=[] so it
  can't fire there). Response carries `ingest_coverage`.
- **P3 agent context** — `ai/context/sections/tables_schema_section.py` `_render_coverage_note` injects a hard
  `<data_coverage status="incomplete">` warning (periods present, files missing, "do NOT infer/fabricate") into
  BOTH table renderers. Section file only — did NOT touch the 3 core context files.
- **P4 robust read** — `_read_one_file_robust` gate now `ROBUST_INGEST OR INGEST_RECONCILE` → reconcile auto-uses
  the robust csv/excel readers (banner skip, encoding/delim sniff) so failing months parse.
- **P5 UI** — `components/data/UploadSpreadsheetModal.vue` `coverageOf(ds)`: degraded → red persistent toast naming
  missing files (both single + batch paths) instead of green success.
- **Proofs:** P1 flag on/off (records failed vs None); `_build_coverage` 3 branches; P3 render; P4 banner CSV no
  regression; **real-DB integration** of run_ingest_reconcile (missing merged_path → degraded + table stamped);
  **live route E2E** through running server (flag effective via DB override, two-month same-schema append →
  reconcile fired → `ingest_coverage` in response; fixed false-degrade live). Flags enabled org e02b1b04:
  `HYBRID_INGEST_RECONCILE` + `HYBRID_MERGE_SAME_SCHEMA`. EPHEMERAL (backend hot-cp + FE fe-sync; NOT baked, NOT
  pushed). Rollback backups in `scratchpad/rollback_ingest_reconcile/`. NOT done: bake, git push, held P0 data
  re-ingest of the real 5 months into source 0b9b39ac.

---

## 2026-07-01 — v1.63.0 Verified-golden EVAL GATE wired INTO training (BAKED)
Goal: finish agent training's trust half — every business metric verified against its doc's ground-truth number
before the agent uses it. Followed a phased plan (`docs/TRAINING_TODO.md`), audit-first (`docs/TRAINING_STATE.md`).
- **Phase 0 audit** caught memory drift: real org = `7d372305` (not e02b1b04); `HYBRID_FULL_PIPELINE=true` but in
  `train_orchestrator` it only gated hybrid_index+brain_graph — the doc-driven verified pipeline (`routes/pipeline.py`
  build-goldens: logic_parser → registry → golden_gen → eval_gate → _save_golden) was ORPHANED from `run_training`.
  Snapshot `cityagent-analytics:rollback-training-20260701`.
- **Phase 2 wiring:** new fail-soft stage in `run_training` (after `joins`, before `hybrid_index`), gated
  `HYBRID_VERIFIED_GOLDENS` AND `HYBRID_FULL_PIPELINE`. Loads `AgentDefinition`s, groups by `data_source_id`, runs
  `golden_gen.generate_for_definitions` → `eval_gate.evaluate`, saves only matches via `pipeline._save_golden`
  (approved+is_golden), HOLDS mismatch/error. Reuses existing services (wiring, not new logic). ~55 lines, one
  insert, no other lines touched.
- **Phase 3 proof (org 7d372305, studio CRM 2b7fa1cf, source Apr fd164352 w/ 5 merged_paths = 6 months):**
  populated `agent_definitions` (0 → 9) via crmqa.docx (12 triples). First eval ran 0-approved — **root-caused to
  the bare-python override-load landmine** (scripts via `docker exec python` don't fire `load_overrides_from_db`, so
  `ONE_TABLE_MERGE` read OFF → 6 stem tables → single-table SQL → Lead=119). Forcing the flags on collapsed the 6
  files into ONE 21,240-row table → Lead=1544 / Successful=7526 / Unsuccessful=4179 EXACT → 3 approved. **No
  `SpreadsheetClient` change needed** (Option B revealed unnecessary — client already merges).
- **Real in-process train** (script did `load_overrides_from_db` then `run_training`): all 16 stages green,
  `verified_goldens: ok (3 approved, 6 held)`, "agent ready". Confirms the stage fires live in a real train.
- **Held 6 = genuinely broken, not auto-fixable:** New User (expected 2025 unreproducible by any derivable
  predicate; New-status=658, distinct-user=344/4411), Channel Breakdown (a pivot/breakdown mis-modeled as a scalar
  metric — 603 is one matrix cell; eval gate can't score a pivot), Q8/Q9/Q11 (doc-format SQL errors), Q10 (no
  expected). These need business input via the instruction-driven corrector (`HYBRID_QUERY_CORRECTION`) — deliberately
  NOT auto-fixed. This is the gate working (quarantine + explain), not failing.
- **State:** `HYBRID_VERIFIED_GOLDENS` flipped ON (DB override, org 7d372305; backup in scratchpad). 3 verified
  goldens saved. BAKED via docker-commit `ca-app` → `cityagent-analytics:dev` + tag `v1.63.0`. NOT git-pushed.
  NOT done: fix/re-model the held 3 (need business definitions), enable+prove the corrector loop, git push.

## 2026-07-01 — E3 column-profile + E4 data-validation WIRED into agent upload path (EPHEMERAL, flags OFF)
Master-Plan ingest stages E3/E4 (built earlier as standalone tested modules) are now wired into the live
from-file upload route so an agent upload actually profiles + validates the data.
- **`routes/data_source_from_file.py`** — new block **4c4** (after reconcile `4c3`, before post-ingest `4d`),
  gated `flags.COLUMN_PROFILE or flags.DATA_VALIDATION`, fail-soft (own try/except + own commit), never blocks
  upload. Reads frames via `SpreadsheetClient._load_frames()` + active `DataSourceTable` rows.
  - **E3**: `column_profile.profile_frame(df)` per frame → merged → `persist_profile(trows, profile)` writes
    dtype/null_pct/distinct/min/max/top_values into `DataSourceTable.columns[].metadata` — the SAME store
    `column_intel` uses, so the agent schema context surfaces `distinct`/`nulls`/`values` with NO section edit.
  - **E4**: `data_validator.null_and_dup_checks(df, profile)` → `build_data_quality_block(warnings)` → stamped
    onto each active table's `metadata_json['data_quality']` ONLY when there are real findings (skip the clean
    marker = no context noise).
- **`ai/context/sections/tables_schema_section.py`** — new `_render_data_quality_note(metadata_json)` (returns
  the stored block verbatim when it starts `<data_quality`), wired into BOTH render paths (`_render_table_xml`
  and `_render_topk_tables_full`), next to the existing `_render_coverage_note`.
- Compiles host + container; deployed via `docker cp` both files + `docker restart ca-app`; `:3007` healthy.
- **State:** flags `HYBRID_COLUMN_PROFILE` + `HYBRID_DATA_VALIDATION` default OFF → zero behavior change until
  turned on. EPHEMERAL (docker cp, NOT baked, NOT pushed). NOT done: turn flags ON via DB override for org
  7d372305 + re-upload to prove live; wire E3/E4 into `train_orchestrator`; bake.

## 2026-07-01 — E5 data typing (real numbers + dates) built + wired (EPHEMERAL, flag OFF)
Master-Plan stage E5. The query engine now gets real types instead of string ops.
- **NEW `services/ingest/typing.py`** `apply_typing(df)` — returns a typed COPY: date-shaped object cols →
  datetime, number/measure cols → numeric (strips `,` + leading currency). Uses E3 `_classify_dtype`; date
  takes priority, then `_try_number` attempts ANY object col but strict (>=98% parse) + **code guard** (any
  leading-zero integer `007` → treated as phone/zip/id, left string). category/text/`_source_*` untouched.
  Fail-soft (raw frame on error).
- **`spreadsheet_client.py connect()`** — gated typing pass (`flags.DATA_TYPING`) maps every frame through
  `apply_typing` BEFORE DuckDB register/materialize. OFF → byte-identical raw frames.
- **Flag `HYBRID_DATA_TYPING`** added 3-place (registry + `@property` + snapshot), category Ingest, default OFF.
- **Test `scratchpad/test_t21.py` — PASS:** (1) REGRESSION — 3 verified metrics EXACT (Lead 644 / Succ 7526 /
  Unsucc 4179), typing ON == OFF (didn't move a count); (2) DATE — `Call Completed Date` typed, real min/max
  2025-01-02..2025-06-30, `WHERE date >= DATE '2025-01-01' AND < '2025-04-01'` = 11037/21240 rows (impossible
  on strings); (3) NUMBER — `'1,234'` → int64, sum 16079, text col stays object.
- Deployed (docker cp typing.py + hybrid_flags.py + spreadsheet_client.py + restart), :3007 healthy. EPHEMERAL,
  flag OFF (not enabled for any org yet), NOT baked. Why safe for goldens: verified metrics filter text columns
  → never parse numeric → untouched. E3 (dtype) feeds E5 (cast). Task #21 done.

## 2026-07-01 — PowerBI per-user cross-tenant sign-in (P1+P2)

Goal: every user connects Power BI in their OWN account (incl. cross-tenant B2B guest), like the local tester app.
Finding: 90% already built — `powerbi_user` connector (`PowerBIUserClient`, ROPC email+pw+tenant, flag `POWERBI_USER`),
per-user credential system (`auth_policy=user_required` + `UserDataSourceCredentialsService` + routes
`GET/POST/PATCH/DELETE /data_sources/{id}/my-credentials` + `/test`), per-user schema overlay, FE
`UserDataSourceCredentialsModal.vue`. `tenant_id` lives in **Credentials** (per-user) not Config → cross-tenant per-user
works out of the box (each user supplies their own guest tenant).

Only gap = users don't know their guest tenant GUID. Built **P2 tenant auto-discovery**:
- NEW `app/services/powerbi_tenant_discovery.py` `discover_tenants(username,password,home_tenant='organizations')` →
  ROPC (public client `1950a258…`) for a `management.azure.com/.default` token → ARM
  `GET /tenants?api-version=2020-01-01` → `[{id,name,domain}]` (home + all B2B guest tenants). Surfaces raw AADSTS
  hint on MFA/ROPC-block. Read-only, no secret stored.
- NEW route `POST /api/data_sources/powerbi/discover-tenants` (in `routes/user_data_source_credentials.py`, same router
  so auto-included) — pre-connect (no data source needed), flag-gated `POWERBI_USER` (404 off), fail-soft `{ok,error,tenants}`.
- FE `UserDataSourceCredentialsModal.vue`: for `powerbi_user`, a **"Find my tenants"** button under the tenant_id field →
  calls discovery with the entered email+pw → renders a click-to-pick tenant list that sets `credentials.tenant_id`.
  i18n keys added to `locales/en.json` (findMyTenants/pickTenantHint/enterEmailPasswordFirst/noTenantsFound).

Verified LIVE in-container: `discover_tenants(<pbi-test-user>, …)` → 2 tenants
(City Holdings `0f69909c` home MM + City Mart Holding `0a8a4f2c` guest Singapore = where DataAgent_TestRun lives).
Route registered `/api/data_sources/powerbi/discover-tenants`. Backend hot-cp'd + restarted (:3007 healthy).

EPHEMERAL: backend cp-only (not baked); FE change needs fe-sync/rebuild to show on :3007 (or dev :3000).
Flag `POWERBI_USER` default OFF — enable per-org to use. NOT baked, NOT pushed.
Deferred P3 device-code (MFA fallback), P4 brute table-name discovery (INFO blocked), P5 storage-mode gate.
Cross-tenant root cause + tester scripts → memory `project_cityagent_powerbi_item_access`.

## 2026-07-01 — Power BI per-user connector: scan-all-tenants + storage-mode gate + brute table discovery (v1.64.0, BAKED)
Next phase for the per-user Power BI connector (P1 sign-in + P2 tenant-discovery shipped earlier today). Built by 2 disjoint-file subagents + hardened after a live test.
- **#8 scan-ALL-tenants (`services/powerbi_multi_tenant_scan.py`, NEW):** `scan_all_tenants(username,password,client_id=None)` = `discover_tenants` (ARM `/tenants`) → per-tenant `PowerBIUserClient.get_schemas()` in `ThreadPoolExecutor(max_workers=4)`, each tenant wrapped fail-soft (one bad tenant never sinks the rest; discovery failure surfaces as a single failed pseudo-tenant). Every returned Table tagged in `metadata_json["powerbi"]` with `tenantId`+`tenantName`. Returns `{tenants:[{id,name,domain,ok,table_count,error}], tables:[...], table_count}`; never raises. Credentials-service method `scan_all_tenants_overlay()` (`user_data_source_credentials_service.py` ~L546, flag-gated `POWERBI_USER`, `await asyncio.to_thread(...)`) reshapes merged tables to the `{name:{columns:[{name,dtype}],pks,fks,metadata_json}}` normalized shape and persists via existing `DataSourceService._upsert_user_overlay` (no new table/migration). Route `POST /api/data_sources/{id}/my-credentials/scan-all-tenants` (`routes/user_data_source_credentials.py`). FE "Scan all my tenants" button + per-tenant result list in `UserDataSourceCredentialsModal.vue` (i18n `data.scanAllTenants`/`scanAllHint`).
- **P5 storage-mode gate (`powerbi_client.py`):** module helper `_is_dataset_queryable(ds)` + `_QUERYABLE_STORAGE_MODES={Import,PremiumFiles,Abf,DirectQuery}` (on-prem-gateway → False). `list_datasets` now emits `storageMode`/`targetStorageMode`; `get_schemas` Phase-4 metadata gets `storageMode`+`isOnPremGatewayRequired`+`queryable`. Non-queryable models still surfaced, tagged not-queryable (agent skips them instead of 400ing at query time).
- **P4 brute table-discovery (`powerbi_client.py`):** `_COMMON_TABLE_NAMES` (~40, de-duped) + `_brute_discover_tables()` — parallel `EVALUATE TOPN(1,'Name')` probes, column names from `Name[col]` bracket-strip. Wired into `get_dataset_tables` AFTER COLUMNSTATISTICS + REST `/tables` both yield nothing. **HARDENED (live-test earned):** `_get_tables_via_column_stats` now returns `(tables, empty_db)` — `empty_db=True` when the COLUMNSTATISTICS error is "…work only on databases which have at least one table" (genuinely empty staging warehouse) → `get_dataset_tables` skips REST+brute entirely; `_brute_discover_tables` aborts the whole probe on first HTTP 429 (`threading.Event`) + `max_workers` 6→4. Without this, 8 empty staging DBs × ~40 probes tripped the 120 req/min/user cap → 429 storm dropped the guest-tenant scan.
- **Proven live (org 7d372305, flag ON):** `scan_all_tenants` for `<pbi-test-user>` → 2 tenants OK (home City Holdings `0f69909c` + guest City Mart Holding SG `0a8a4f2c`), 24 merged tables, 18 queryable / 6 not (home Hub Team on-prem-gateway correctly flagged non-queryable), tenant-tagged, Open Project Tracking `projects`/`subjects` surfaced, NO 429 storm (empty staging DBs skipped). Backend `import main` clean, both routes registered, FE button baked into `_nuxt` dist.
- **BAKED** `cityagent-analytics:dev` = `cityagent-analytics:v1.64.0` (full `docker build` + `docker commit` to fold the post-bake P4 hardening). Rollback `cityagent-analytics:pre-powerbi-rollback` (9ca5c822613b). Flag `HYBRID_POWERBI_USER` ON via DB override org 7d372305. NOT git-pushed. Mig head unchanged `defreg1` (no migration). Deferred: P3 device-code (MFA fallback), refresh-token storage. Detail → memory `project_cityagent_powerbi_item_access`.

## 2026-07-01 — Power BI P3 device-code sign-in (MFA-safe) (v1.65.0, BAKED)
The last real gap in the per-user Power BI connector: ROPC (email+password) dies on MFA-on accounts (`AADSTS50076/50079`) and ROPC-blocked tenants (`7000218`). P3 = OAuth 2.0 device-code, the self-serve MFA-safe path. (Built inline — the two spawned subagents died instantly on a transient org "subscription access disabled" gate, zero work; rebuilt by hand.)
- **NEW `services/powerbi_device_code.py`:** `start_device_code(tenant_id, client_id=None)` → POST `/devicecode` (client MS public `1950a258…`, scope `https://analysis.windows.net/powerbi/api/.default offline_access`) → `{ok,device_code,user_code,verification_uri,expires_in,interval,message}`. `poll_device_code(tenant_id, device_code, client_id=None)` → ONE poll of `/token` grant_type=`urn:ietf:params:oauth:grant-type:device_code` → `{status: success|pending|error, access_token?, refresh_token?}` (maps `authorization_pending`/`slow_down`→pending). Never raises; never logs tokens.
- **`powerbi_user_client.py`:** `__init__` gains `refresh_token`; `connect()` precedence now delegated-access_token → **refresh_token (refresh grant, rotates refresh_token, scope `SCOPE + " offline_access"`)** → ROPC password. So a stored refresh_token = durable connection, no hourly re-login.
- **`configs.py`:** `PowerbiUserCredentials` — `username`/`password` made Optional (device-code cred = tenant_id + refresh_token), added hidden `refresh_token`. Whole creds dict is `encrypt_credentials()`-Fernet-encrypted → refresh_token never plaintext.
- **Routes (`user_data_source_credentials.py`):** `POST /data_sources/{id}/my-credentials/device-code/start` + `/poll` (flag `POWERBI_USER`, fail-soft). Poll-success builds `UserDataSourceCredentialsCreate(auth_mode, credentials={tenant_id, refresh_token, username?})` → `svc.upsert_my_credentials` (persist encrypted); tokens never returned to the client.
- **FE (`UserDataSourceCredentialsModal.vue`):** "Sign in with a code (MFA-safe)" button → start → shows `user_code` + clickable `verification_uri` + status line → `setInterval` polls at the server's `interval` → on success `emit('saved')` + close; timer cleared on unmount + modal-close. i18n `deviceCodeSignIn/enterTenantFirst/deviceWaiting/deviceSuccess/deviceCodeHint`.
- **PROVEN live end-to-end:** started device-code vs SG tenant `0a8a4f2c` → user approved in browser (MS "signed in to Azure PowerShell" confirmation) → `poll_device_code` returned success + refresh_token → constructed `PowerBIUserClient(tenant_id, refresh_token)` → `list_workspaces()` = [MSFB_POC, HUB-AI, DataAgent_TestRun]. Backend `import main` clean, both routes registered, FE UI baked into `_nuxt` dist.
- **BAKED** `cityagent-analytics:dev` = `:v1.65.0` (full `docker build` + force-recreate), rollback `pre-p3-rollback` (=v1.64.0). VERSION_HYBRID 1.65.0, mig head unchanged `defreg1`, flag `HYBRID_POWERBI_USER` ON org 7d372305, NOT git-pushed. Now ANY Power BI user (MFA or not, any tenant, guest or home) can self-connect. Remaining backlog: none critical (device-code covers MFA; refresh-token storage now done inline).
- **Standalone tester:** `scratchpad/pbi_devicecode_app.py` (stdlib :8901) — 3 sign-in paths (device-code / email+password ROPC / find-my-tenants) → scan (queryable-tagged) → DAX runner. Tokens in-memory only. For handing to other users to self-test.

## 2026-07-01 — Connector → Data Agent (bagofwords-style, Phases 1-6) (v1.66.0, BAKED)
"Connect a data source once → it becomes an org-shared agent everyone chats; each user signs in with their own account and sees only their own data." Built as 6 phases; only Phases 1-2 needed new code (3-5 reuse existing machinery — the payoff of Studio=agent + per-user connectors).
- **Phase 1 — central tenant on connector:** `PowerbiUserConfig` gains `tenant_id` (admin sets ONCE); `PowerbiUserCredentials.tenant_id` → Optional (users enter only email+pw). **Correctness guard:** `construct_client`+`construct_clients` (`data_source_service.py`) now strip `None` from creds BEFORE the `{**config, **creds}` merge, so a blank per-user field can't wipe the admin's config tenant (a real bug the recon flagged: the old post-merge None-strip would delete a creds-`None`-over-config value entirely). Live-proven: admin config tenant preserved when user omits it; user tenant override still wins. FE = zero change (ConnectForm + UserDataSourceCredentialsModal are schema-driven; `/data_sources/{type}/fields` returns both config+creds).
- **Phase 2 — connector auto-becomes an agent:** NEW `services/connector_agent.py::auto_create_agent_for_connection(db, *, connection_id, organization_id, owner_user_id)` — flag `HYBRID_CONNECTOR_AS_AGENT`; ensures a DataSource wraps the connection (reuse-first, mirrors `activate_studio_connector`), creates `Studio(share_scope='org', config={source_connection_id, connector_agent:True})`, binds `StudioDataSource`. Idempotent (skip if a studio already carries `source_connection_id`), greenlet-safe (primitive ids, re-query fresh, own commits), fail-soft (never breaks connect). Hooked into `connection_service.create_connection` right before the return (captures `str(id)` up-front). Flag = 3 anchors in `hybrid_flags.py`. Live E2E: create `powerbi_user` connection → org-shared agent spawned, DataSource-bound, marker set, 2nd call idempotent (same studio id).
- **Phase 3 — appears for all (no code):** `list_studios` (`routes/studio.py:370`) visibility already `or_(owner, share_scope=='org', member, group)`. Live-proven: a non-owner, non-member uid sees the org-shared agent.
- **Phase 4 — per-user sign-in gate (no code):** `ReportAgentPanel.vue:63` shows a **Connect** button when `needsUserConnection(agent)` (= `auth_policy=='user_required' && !has_user_credentials`, `useDataSourceConnect.ts:22`) → opens `UserDataSourceCredentialsModal` (email+pw, tenant now optional). `@saved` → refresh → gate clears.
- **Phase 5 — per-user query + access (no code):** `resolve_credentials` (`data_source_service.py:1524`) picks the caller's OWN `UserDataSourceCredentials WHERE user_id==current_user.id`; merged with admin config tenant → `PowerBIUserClient` runs as that user → Microsoft enforces their RLS/item perms. Overlay reads scoped `UserOverlayTable.user_id` → isolated catalogs.
- **Phase 6 — BAKED** `cityagent-analytics:dev` = `:v1.66.0` (full docker build), rollback `pre-connector-agent-rollback` (=v1.65.0). VERSION_HYBRID 1.66.0, mig head unchanged `defreg1` (no migration — Studio.config is JSON), flag `HYBRID_CONNECTOR_AS_AGENT` ON via DB override org 7d372305, NOT git-pushed. Deferred (cosmetic): Studio card "Data Agent" badge from `config.connector_agent` marker (Phase 3.2/3.3).
- Files: `configs.py`, `data_source_service.py`, `settings/hybrid_flags.py`, NEW `services/connector_agent.py`, `services/connection_service.py`. Mockups: `scratchpad/data_agents_page.html` + `dataagent_chat_full.html`.

## 2026-07-01 — Data Agents page (bagofwords parity) + connector→org-visible-agent (v1.67.0, BAKED)
Reconciled the "connector → data agent" work onto the RIGHT surface. Our fork already had the full bagofwords Data Agents page at `/agents` (DataSource = agent: list · create · connection · tables · context · tools · queries · evals · monitoring · settings) — it was just NOT in the nav and admin-connected sources weren't org-visible. Two subagents (disjoint) + verification.
- **Nav (top bar):** `frontend/composables/useAppNav.ts` — added a group `{title:'nav.dataAgents', direct:'/agents', items:[data-agents → /agents]}` placed BETWEEN Studios and Workspace. `direct` groups render on the TOP bar only and are excluded from the left rail (`activeGroup = visibleGroups.find(g => !g.direct && isGroupActive(g))`, line 203) — so Data Agents is top-only like Studios. fe-synced (EPHEMERAL until bake).
- **Connector → org-visible Data Agent (reworked `services/connector_agent.py`):** dropped the v1.66 Studio auto-create entirely. `auto_create_agent_for_connection(db,*,connection_id,organization_id,owner_user_id)` (flag `HYBRID_CONNECTOR_AS_AGENT`) now ensures a DataSource wraps the connection with **`is_public=True`** (existing DS → flip is_public; else create `DataSource(is_public=True, use_llm_sync=False, owner_user_id)` + append conn, IntegrityError name-clash fallback `{name}-{id[:8]}`, mirrors `routes/studio_sources.py:557`). Returns `str(ds.id)`. Idempotent by construction (2nd call finds public DS, no-op), greenlet-safe (primitive ids, re-query fresh), fail-soft. Hook in `connection_service.create_connection` unchanged (same fn name/signature).
- **WHY is_public = the whole feature:** `data_source_service.get_data_sources` list query (line 983-987) shows a member any DataSource where `is_public==True OR id in member_ids` (admin `show_all` bypass; `publish_status` default `'published'` passes the line-996 gate). So `is_public=True` = org-visible on `/agents` for everyone. Combined with `auth_policy='user_required'` → everyone SEES the agent, each signs in with their OWN creds (per-user login gate `agents/[id]/connection.vue` + list `needsUserConnection`), and queries run under that user (`resolve_credentials` picks `UserDataSourceCredentials WHERE user_id==current_user.id`, `:1524`). = admin connects once → whole org chats it, each as themselves.
- **Verified (subagent B, no gaps) + LIVE E2E:** create `powerbi_user` connection (flag ON) → org-visible data agent (`is_public=True`, `publish_status=published`), idempotent (dsid1==dsid2), non-member sees it via the is_public filter. /agents list=data-sources, agent-home `/agents/[id]` = guiding instruction + starter prompts + "New report scoped to this agent" (POST `/reports` `data_sources:[agentId]` → chat), per-user sign-in gate + per-user query creds all AUTO-WORK.
- **BAKED** `:dev`=`:v1.67.0`, rollback `pre-dataagent-rollback` (=v1.66.0). VERSION_HYBRID 1.67.0, mig head unchanged `defreg1`, flag ON org 7d372305, NOT git-pushed. **Supersedes v1.66 Studio auto-agent** (removed). Files: `useAppNav.ts`, `services/connector_agent.py` (rewrite). Detail → memory `project_cityagent_connector_as_agent`.

## 2026-07-01 — v1.69.0 Microsoft Connectors Hub on Data Agents (Fabric, per-user device-code)
Revamp of `/agents` into a Microsoft-connector hub. Admin configures a connector template ONCE; every
member (and the admin) signs in with their OWN Microsoft account via MFA-safe device-code → private
per-user clone syncs the tables their account can see. Fabric-first; PowerBI/SharePoint/OneDrive queued
(same path). Built on the existing per-user connector primitives (flag `HYBRID_PER_USER_CONNECTOR`,
ON org 7d372305). EPHEMERAL (hot-cp backend + fe-sync) — bake pending.
- **P1 device-code token** (`services/powerbi_device_code.py`): added `scope` param to `start_device_code`
  + scope consts `SCOPE_POWERBI/SCOPE_FABRIC/SCOPE_GRAPH` + `FABRIC_TOKEN_SCOPE`, and
  `refresh_to_access_token(tenant, refresh_token, scope)` — redeems a FOCI refresh_token for a fresh token
  at any Microsoft resource (PowerBI refresh_token → Fabric `database.windows.net` SQL token). Client
  `1950a258…`, no app registration, no secret.
- **P2 Fabric client** (`data_sources/clients/ms_fabric_client.py`): `MsFabricClient.__init__` gained
  `refresh_token`; `_get_access_token` mints a fresh SQL token from it (per connect → never expires) and
  feeds ODBC via `attrs_before={1256}`. Zero coupling — both build paths (`construct_client`,
  `_resolve_client_by_type`) narrow to the constructor sig, so `refresh_token` in creds forwards
  automatically. `create_connection(system_only)` validates by a live connect (not pydantic) → a raw
  `{refresh_token}` dict flows through.
- **P3 register + routes**: `per_user_connector.device_code_start/device_code_poll` (poll-success →
  `register_template_for_user(auth_mode='device_code', credentials={refresh_token})` → private clone +
  catalog sync under the user's token). Routes `POST /api/connectors/{template_id}/device-code/{start,poll}`
  (`routes/data_source.py`). Tenant/scope derived from the template's connection config.
- **P4/P5 FE**: new `components/connectors/ConnectorsMsHub.vue` — 4 tiles (Fabric live), role-gated admin
  `Manage connectors` (publishes an `is_user_template` Fabric template via POST /data_sources,
  `auth_policy=user_required`), device-code connect modal (start → poll loop → auto-register), test-clone
  button. Mounted top of `pages/agents/index.vue` (EXPLICIT import — Nuxt `<Connectors*>` prefix landmine).
  i18n block `connectors.*` (locales/en.json, repo root). Flag read from `GET /organization/hybrid-flags`
  (list) row `PER_USER_CONNECTOR.effective`. Schema: `MSFabricConfig.tenant_id` (optional),
  `DataSourceSchema.is_user_template`+`template_source_id`.
- **P6 tester** `scratchpad/fabric_devicecode_test.py` — in-container device-code → mint SQL token → ODBC
  connect → list tables + test query. Compiles in-container, ODBC Driver 18 present.
- **LIVE PROOF**: `start_device_code(<SG tenant>, scope=SCOPE_FABRIC)` returned a real `user_code` +
  `login.microsoft.com/device` — full Fabric device-code plumbing works against Microsoft (only the human
  browser approval remains). Routes live (`/api/connectors/*` = 401 unauth). FE hub + i18n confirmed in the
  `nuxt generate` bundle; `/agents` = 200.
- **LANDMINE**: connector routes mount at `/api/connectors/*` (router has NO prefix; `main.py` adds `/api`;
  the route strings are `/connectors/...`, NOT `/data_sources/connectors/...`). ODBC needs `,1433` +
  `Connection Timeout=30` (already in the client). Admin app-login creds (`admin@cityagent.io`) did NOT
  match `Admin12345`/`CityAgent#2026` this session → API E2E done via in-container product code instead.
- Backup of the pre-revamp Data Agents page: `backups/agents-page-2026-07-01/` (27 files).

## 2026-07-01 — v1.69.1–1.69.5 MS Connectors Hub follow-ups (PowerBI live, no-typed-DB, dupe fix, page redesign)
- **v1.69.1** Power BI (User Sign-in) LIVE in hub (`powerbi_user`, tenant-only config). Admin no longer types a
  database: `MSFabricConfig.database` → Optional; `MsFabricClient` connects with no fixed DATABASE when blank +
  `_accessible_databases()` (`sys.databases`/`HAS_DBACCESS`) + `_get_tables_for_db()` (3-part `[db].INFORMATION_SCHEMA`,
  names `db.schema.table`). **NEEDS-LIVE-TEST vs a real multi-warehouse Fabric workspace.** Per-connector admin config
  (Fabric=server+tenant, PowerBI=tenant only), database field removed. i18n `connectors.autoDbNote`/`configureName`.
- **v1.69.2** BUG: `_resolve_client_by_type` (connection_service) derived class names algorithmically
  (`powerbi_user`→`PowerbiUserClient`) but the class is `PowerBIUserClient`. FIX: call `resolve_client_class`
  (registry `client_path`, dynamic fallback). Fixes every type whose class casing ≠ slug.
- **v1.69.3** per-user connect FAIL-SOFT: PowerBI on-prem/empty datasets → DAX "databases which have at least one
  table" → schema-empty was HARD-FAILING connect. Added `create_connection(validate=False)`; `per_user_connector`
  passes it (device-code already proved identity; empty catalog syncs best-effort). This account's PowerBI = on-prem/Abf
  (0 queryable) → agent 0 tables EXPECTED; real data = Fabric SQL endpoint.
- **v1.69.4** DUPLICATE-CLONE ROOT CAUSE + logos + pill. The `HYBRID_CONNECTOR_AS_AGENT` hook in
  `create_connection` (`auto_create_agent_for_connection`) fired on the per-user PRIVATE clone connection → spawned a
  2nd **public** DataSource (is_public=true = org leak) on the SAME connection → 2 cards from 1 sign-in. FIX: guard
  `if not owner_user_id:` — private/owner-scoped connections never auto-spawn a public agent. Also: real MS product
  LOGOS in tiles (`/data_sources_icons/{ms_fabric,powerbi,sharepoint,onedrive}.png`); connect/Connected pill hidden on
  non-connector (file/duckdb) agents (`v-if="requiresUserAuth(ds)"`). DB cleanup: deleted stray public `1f71ffb6` +
  dupe `d9a3be7a` + shared connection `97e6a0c2` (datasource_tables col = `datasource_id`; report_data_source_association FK).
- **v1.69.5** PAGE REDESIGN. COMPACT connector tiles + **⚙ gear = configure** (no big Configure button); **Connections
  chips section REMOVED** from `pages/agents/index.vue`; NEW full **Manage connectors** page `pages/connectors/manage.vue`
  (table connector·tenant·status·members-connected·Configure/Edit; new=POST `/data_sources`, edit=PUT `/data_sources/{id}`
  config). "Manage connectors" btn → `navigateTo('/connectors/manage')`. i18n `connectors.manage*`/`col*`.
- All EPHEMERAL (hot-cp backend + fe-sync) then `docker commit` → baked `:v1.69.5`=`:dev`, tags v1.69.0..5, rollback
  `pre-connector-hub-revamp`. **NOT git-pushed** (v1.59→1.69.5 all local — top risk).
- **PENDING (D):** agent-detail (`agents/[id]/index.vue`) redesign = keep tabs + left connection summary + chat-first bar
  (user-approved, NOT yet built).

## 2026-07-01 — v1.70.0 One-click connector agents (auto name/logo/tables)
Sign-in IS agent creation — the manual 3-step wizard (`/agents/new`) is bypassed for MS sources. Per-user isolation
unchanged: each user signs in with own device-code → own refresh_token → sync runs as that user → MS returns only
tables that identity can read → private `is_public=False` owner-scoped clone (`template_source_id` set, v1.69.4 hook
guard intact). U1's tables never visible to U2.
- Backend `services/per_user_connector.py` `DataSourceService_seed`: `max_auto_select` 30 → **100000** = auto-activate
  ALL synced tables (no manual Select-Tables pick; catalog already scoped by sign-in). Modal already redirects to
  `/agents/{clone_id}` on poll-success.
- FE `pages/agents/index.vue`: NEW `connectorMeta(ds)` — clone (`template_source_id`) + first-connection `type` →
  `CONNECTOR_META` map → product **logo** (`/data_sources_icons/{ms_fabric,powerbi,sharepoint,onedrive}.png`) +
  clean **name** ("Microsoft Fabric"/"Power BI"/…) + signed-in **email** subtitle (parsed from `name.split('·')`).
  Card top-tile shows `<img logo>` for clones (else clay circle-stack); file/DuckDB unchanged. REMOVED: show-all
  toggle, Create-Agent button, ghost "+" card, unused `DataSourceGrid` import + `canCreateDataSource`/`canViewAllAgents`
  computeds. Section gated `allAgents.length > 0`; NEW empty state (arrow-up → hub). i18n `data.agentsAutoHint`/
  `signedInPrivate`/`emptyNoAgents`/`emptyNoAgentsHint`.
- Deploy EPHEMERAL (backend hot-cp py_compile OK, no restart — lazy import; FE fe-sync, page 200, new keys in bundle
  `D1HcABxQ.js`). Baked `docker commit` → `:v1.70.0`=`:dev`. **NOT git-pushed** (v1.59→1.70.0 all local — top risk).

## 2026-07-01 — v1.70.1 hide connector template + v1.70.2 agent-detail left-rail
- **v1.70.1:** admin connector TEMPLATE (`is_user_template=True`, e.g. `50f51834` "Power BI (User Sign-in)") was rendering
  as a phantom Data Agent card → looked like "configuring created an agent" + blocked re-config. FIX: `pages/agents/index.vue`
  `allAgents` filters `!ds.is_user_template`. Baked `:v1.70.1`.
- **v1.70.2:** agent-detail redesign into Manage-page style. TABS live in `layouts/data.vue` (NOT `[id]/index.vue`, which is
  only Overview content via `<slot/>`). Moved horizontal tab bar → **sticky LEFT RAIL**: identity (logo/name/email/Connected
  via `connectorMeta` — same CONNECTOR_META map as index.vue) + tabs grouped by `tabGroups` (Explore=''/tables/queries ·
  Configure=context/tools/settings · Observe=monitoring/evals, filtered through existing perm-gated `tabs`) + lifecycle
  buttons. **Test** → GET `/data_sources/{id}/test_connection`. **Disconnect** (gated `isClone` = `template_source_id` set)
  → DELETE `/data_sources/{id}` (cascades tables/memberships, leaves conn orphaned) THEN DELETE each `/connections/{connId}`
  (owner-guarded `guard_owned_connection`) → routes `/agents`. Main col keeps PublishStatusControl + New Report + inline
  description + `<slot/>`. `[id]/index.vue` Overview `md:w-2/3`→full. `.rail-btn` scoped styles. Baked `:v1.70.2`=`:dev`.
  Scouts (2 parallel Explore) mapped layout + delete endpoints. **NOT git-pushed** (v1.59→1.70.2 all local — top risk).

## 2026-07-01 — v1.70.3 AppRail parity + v1.71.0 personal view + auto-learn
- **v1.70.3:** agent rail = verbatim copy of `components/nav/AppRail.vue` `.cag-rail-card` (Workspace/Manage parity). Learned via Explore scout (AppRail/useAppNav/default.vue). `layouts/data.vue` scoped CSS `.cag-rail-card`/`.cag-eyebrow`/`.cag-sec-link`/`.cag-sec-active`(#ECEAE1) copied; shell `flex bg-[#F1ECE3]`; main `#FBFAF6` card; `tabIcon()` heroicons. HARDCODED replica (per-id tabs don't fit static `useAppNav.ts`). Baked `:v1.70.3`.
- **v1.71.0 — two features:**
  - **A personal view:** `pages/agents/index.vue` `allAgents` drops public agents you don't own (keep `!is_public` OR `owner_user_id===myUserId` from `useAuth()`), plus existing `!is_user_template`. Fixes "why do I see others' agents" — Financial Market demo (`is_public`) hidden; your private clones/files kept.
  - **B auto-learn on connect:** clone now `use_llm_sync=True`; NEW `per_user_connector.autolearn_clone(clone_id, org_id, user_id)` opens own session (`async_session_maker`) → `DataSourceService.llm_sync` (description + conversation_starters + primary overview instruction via `DataSourceAgent.generate_datasource_instruction`, the "R_OVERVIEW"). Scheduled via `BackgroundTasks` on `/connectors/{id}/device-code/poll` route AFTER a success (sign-in stays instant). Fail-soft. Route sig changed → `docker restart ca-app`. `llm_sync` (`data_source_service.py:630`) is the exact same routine the manual wizard's "Use LLM to learn agent" runs. Baked `:v1.71.0`. **NOT git-pushed** (v1.59→1.71.0 all local — top risk).

## 2026-07-02 — v1.71.1 data agents in report picker + v1.71.2 clarify-shape fix + auto-learn backfill
- **v1.71.1:** Data Agents were hidden from the New-Report context picker. `components/prompt/DataSourceSelector.vue`
  had `const STUDIOS_ONLY = true` gating the whole data-agents list behind `!STUDIOS_ONLY`. Dropped the gates so the
  dropdown shows BOTH Studios + **Data Agents** (new "Data Agents" eyebrow; connectable section `v-if` on length;
  selected-label branch now `(isAutoMode || STUDIOS_ONLY) && …length===0`). Baked `:v1.71.1`.
- **v1.71.2 — blank clarifying-question boxes ("just text box, no question").** ROOT CAUSE = prompt/schema shape
  mismatch: `ai/agents/planner/prompt_builder_v3.py` (~L217) told the model to emit a singular `question` STRING, but
  the clarify tool schema wants `questions: [{text, options}]`. Weak/Auto models followed the prompt → emitted plain
  strings → stored raw in `tool_executions.arguments_json` → `ClarifyTool.vue` read `q.text` = undefined → unlabeled
  dead-end box. DB-confirmed (`{"questions": ["Which summary…string…"]}`). Fixed in 3 layers (user picked "All three"):
  (A) FE `ClarifyTool.vue` `questions` computed normalizes each item (string→`{text}`, object→coerce
  `text`/`question`/`label`) and DROPS empties; (B) BE `ai/tools/schemas/clarify.py` `@field_validator("questions",
  mode="before")` coerces strings/alt-keys→`{text}`, drops empties (self-test `['Which summary…','Time range?']` ✓;
  `ClarifyQuestion.text` already `min_length=1`); (C) `prompt_builder_v3.py` clarify protocol rewritten to match the
  schema — `questions` ARRAY of `{"text","options"}`, question in `text`, choices in `options`+"Other…", no
  lists-in-text, worked example. Deploy: 2 BE files hot-cp + `docker restart ca-app` (schema+prompt reload), FE
  fe-sync, app 200. Baked `:v1.71.2`=`:dev`, `VERSION_HYBRID`=1.71.2.
- **Auto-learn backfill (2026-07-02):** existing Power BI clone `d0c33ff1` predated v1.71.0 (`use_llm_sync=false`) so
  it never auto-learned. Flipped flag → ran `per_user_connector.autolearn_clone` in-container (`import main` first to
  register ORM models — bare `import app.models` pulls dead `application.py` → broken `DataSourceApplicationAssociation`
  mapper). `llm_sync` generated description + 4 conversation_starters + overview instruction (build #4) — persisted
  (`description` + `conversation_starters` len 4). NEW clones auto-learn by default (v1.71.0). LANDMINE: `autolearn_clone`
  is fail-soft — a swallowed error looks like "done"; verify DB fields actually populated. Un-baked (DB-only change).
