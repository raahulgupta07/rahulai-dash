# CODEBASE_MAP — CityAgent Analytics

> **Expert primer. Read this instead of scanning the tree.** Load-bearing 20% only: entry points,
> extension patterns, route mounts, top landmines. Auto-loaded via `@docs/CODEBASE_MAP.md` in CLAUDE.md.
> Companion: `CLAUDE.md` (rules/current state), `DEVLOG.md` (dated history), `ROADMAP.md` (forward plan),
> `docs/INGEST_BRAIN_DESIGN.md` (F09 universal-ingest design).
> **Keep current:** when a ship changes a load-bearing path/pattern, update this file (same habit as DEVLOG bump).
> Last verified: 2026-07-01 · `VERSION_HYBRID` 1.69.5 · mig head `peruser_tmpl1`.
> v1.69.1–5: PowerBI (User Sign-in) LIVE in hub (`powerbi_user`); admin no-typed-DB (`MSFabricConfig.database`
> optional + `MsFabricClient._accessible_databases`/`_get_tables_for_db`, NEEDS-LIVE-TEST); COMPACT tiles + ⚙gear;
> Connections chips REMOVED; NEW `pages/connectors/manage.vue`. LANDMINES: private (owner_user_id) conns must skip
> the CONNECTOR_AS_AGENT hook (`if not owner_user_id:` in create_connection — else dupe+public-leak);
> `_resolve_client_by_type`→`resolve_client_class` (client_path, not name-derive); per-user connect
> `create_connection(validate=False)` (empty PowerBI catalog must not hard-fail).
> v1.69.0: **MS Connectors Hub on `/agents`** (BAKED, rollback `pre-connector-hub-revamp`) — admin configs a
> Fabric TEMPLATE once (`is_user_template=True` DataSource + `auth_policy=user_required` Connection), each user
> signs in via **device-code** (FOCI `1950a258…`, no app-reg) → private per-user clone syncs under their token.
> `powerbi_device_code.py` scope-parametric + `refresh_to_access_token()`; `MsFabricClient(refresh_token=)` mints
> Fabric SQL token→ODBC `attrs_before={1256}`. Routes **`/api/connectors/*`** (`device-code/{start,poll}` +
> `available` + `register`; router NO prefix, main.py adds `/api`). FE `components/connectors/ConnectorsMsHub.vue`
> (explicit import) top of `pages/agents/index.vue`. Flag `HYBRID_PER_USER_CONNECTOR`. Detail → memory
> `project_cityagent_ms_connector_hub`.
> v1.67.0: **Data Agents page** (bagofwords parity) — `/agents` (DataSource=agent: list/create/connection/tables/
> context/tools/queries/evals/monitoring) surfaced in TOP nav between Studios & Workspace (`useAppNav.ts` `direct:'/agents'`,
> top-bar-only). `services/connector_agent.py` reworked: connector-connect → DataSource `is_public=True` (flag
> `HYBRID_CONNECTOR_AS_AGENT`, Studio path REMOVED). `is_public` (see agent, `get_data_sources:983`) + `user_required`
> (own login) = admin connects once → whole org chats, each as self. Supersedes v1.66 Studio.
> v1.66.0: **Connector → Data Agent** (flag `HYBRID_CONNECTOR_AS_AGENT`) — on connection-create,
> `services/connector_agent.py::auto_create_agent_for_connection` auto-spawns an org-shared Studio
> bound to the connection (idempotent via `Studio.config.source_connection_id`, greenlet-safe, fail-soft;
> hooked in `connection_service.create_connection`). Power BI `tenant_id` moved to `PowerbiUserConfig`
> (admin sets once), optional in creds; `construct_client(s)` strip None-from-creds pre-merge so a blank
> per-user field can't wipe the admin tenant. Phases 3-5 = reuse (org-list, `ReportAgentPanel` sign-in
> gate, per-user `resolve_credentials`). Flag ON org 7d372305.
> v1.65.0: Power BI P3 device-code sign-in (MFA-safe, BAKED) — `services/powerbi_device_code.py` (start/poll,
> offline_access→refresh_token), routes `POST /data_sources/{id}/my-credentials/device-code/{start,poll}`
> (poll-success persists Fernet refresh_token), `PowerBIUserClient.refresh_token` + refresh-grant in `connect()`,
> FE "Sign in with a code" button. Flag `POWERBI_USER`. Tester `scratchpad/pbi_devicecode_app.py` (:8901).
> v1.64.0: Power BI per-user connector next phase (BAKED) — `services/powerbi_multi_tenant_scan.py::scan_all_tenants`
> (loop `get_schemas()` per discovered tenant → merged tenant-tagged overlay), P5 storage-mode gate + P4 brute
> table-discovery in `powerbi_client.py` (`_is_dataset_queryable`, `_brute_discover_tables`; hardened skip-empty-DB +
> abort-on-429). Route `POST /data_sources/{id}/my-credentials/scan-all-tenants`. Flag `POWERBI_USER` ON org 7d372305.
> v1.63.0: verified-golden EVAL GATE wired into `ai/knowledge/train_orchestrator.run_training` (stage after
> `joins`, before `hybrid_index`; gated `HYBRID_VERIFIED_GOLDENS`+`HYBRID_FULL_PIPELINE`) — loads
> `AgentDefinition`s → `services/train/golden_gen`→`eval_gate` → saves matches via `routes/pipeline._save_golden`,
> HOLDS mismatch. See `docs/TRAINING_TODO.md` + `TRAINING_STATE.md`. Offline flag-test LANDMINE: bare
> `docker exec python` skips `load_overrides_from_db` (flags read OFF) — `set_override`/load first.

## v1.41.0 live training log (CLI) + AI column meanings + SOON cards
- **Train log:** `ai/knowledge/train_orchestrator.py` keeps a capped timestamped `log[]` in `_train_status`. A
  per-run `_RunLogHandler` (attached to loggers `app.ai.knowledge`/`app.ai.llm`/self, detached in `finally`)
  captures the trainer + LLM-client lines (model/tokens/counts); plus explicit `_log()` markers (`▸ <stage>`,
  default-model, done/failed). `_LOG_CAP=400` in-proc, `_LOG_PERSIST_CAP=200` mirrored to DB. New
  `reset_status()` + `POST /studios/{id}/train/reset` (clears a stuck `running` status). FE
  `pages/studios/[id]/index.vue`: inline panel under the "3 · TRAIN" card — Logs⇄Steps toggle, warm-dark
  `#1b1813` terminal (mono, auto-scroll, level colors), %-bar, Reset/Retry, on-mount `loadTrainStatus()`.
- **AI column meanings (closed a real gap):** NOTHING auto-wrote `SemanticColumn.meaning` before (manual PATCH
  only — `knowledge.py:165` seeds `meaning=""`). New `propose_column_meanings(db,*,organization,data_source,
  model,llm_inference=None)` + `build_column_meaning_prompt()` in `ai/brain/knowledge_proposer.py` (LLM → blank,
  non-approved columns → `status='pending'`, never overwrites approved, returns `{"columns":[ids]}`, fail-soft).
  Route `POST /api/knowledge/ai-suggest-columns/{ds}` (gated `SEMANTIC_LAYER`, placed BEFORE the `/{kind}/{id}`
  catch-all). Folded into the Auto-train `semantic_metrics` stage (per-source, auto-approved like sem/met;
  detail → `N col meanings`). FE `components/knowledge/SemanticTab.vue` "Suggest column meanings" button.
- **Cards:** `reports/[id]/index.vue` Infographic + Insight Map → dimmed `SOON` non-clickable (Excel stays live).
- LANDMINE: column meanings still need APPROVAL to inject (review gate). Standalone route writes pending;
  Auto-train auto-approves. LANDMINE: a fresh/new org has ZERO `hybrid_overrides` → all Intelligence tabs show
  "Enable…" placeholders; set `organization_settings.config.hybrid_overrides` + restart (boot loads them).

## v1.38–1.39 one-click artifacts (HYBRID_ONECLICK_ARTIFACTS — was HYBRID_SLIDE_DECK)
`routes/report_slides.py` turns the empty Dashboard/Slides/Excel right-panel views into one-click builders, no chat.
- `POST /api/reports/{id}/dashboard/generate` (mode='page') + `…/slides/generate` (mode='slides') → shared
  `_generate_artifact(mode)`: resolves org default LLM, runs `CreateArtifactTool` with a MINIMAL hand-built
  `runtime_ctx` (db/report/user/org/model; context_hub/view/head_completion=None, all guarded), reuses the chat
  pipeline (page→React dashboard; slides→python-pptx → `PptxCodeExecutor` → preview PNGs). Deletes its own
  `status='failed'` artifact so it can't flip hasPageArtifact/hasSlidesArtifact with an empty frame.
- `GET /api/reports/{id}/workbook` (read-only, NO LLM) → `{sheets:[{name,columns,rows}]}`, one per query's latest
  success step (`steps.data` parquet-hydrated, cap 5000×50). The `/api/queries` LIST strips step rows, so the Excel
  tab can't build client-side — this feeds it.
- FE `pages/reports/[id]/index.vue`: dashboard CTA branch before page `ArtifactFrame` + slides CTA in the slides
  fallback (both gated `oneClickEnabled` = `/organization/hybrid-flags` `HYBRID_ONECLICK_ARTIFACTS.effective`);
  `excelSheets` prefers `serverSheets` (fetched `/workbook` on mount) over message-scraped `messageSheets`.
  `hasPageArtifact`/`hasSlidesArtifact` key off `a.mode`. Flag OFF → legacy `SlidesPanel`/ArtifactFrame empties.
LANDMINE: `pptx_executor.py` AST gate forbids `getattr` but the slides prompt's `style_chart_text` helper needs it →
`PPTX_ALLOWED_BUILTINS={'getattr','hasattr'}`. LANDMINE: native pptx charts crash on empty categories → slides prompt
DATA SAFETY rule (KPI/text slide for non-categorical vizs).

---

## TL;DR stack
FastAPI (backend, `/app/backend`) + Nuxt3/Vue3 SPA (`/app/frontend`, `ssr:false` → `nuxt generate` static).
Postgres 18 + pgvector. Redis. LLM = **OpenRouter only** (Dash `custom` provider, Fernet key per org).
Container `ca-app` (host :3007 → internal 3000), `ca-postgres` (:5439), `ca-redis`. DB `dash`/`dash`/`dashpassword`.
Admin `admin@cityagent.io`/`Admin12345`. Org 55278108-547e-4546-b2bc-e72c6f92320e (flags ON via DB overrides).
**Stack file = `docker-compose.build.yaml` ONLY** (plain `docker-compose.yaml` = different project = empty DB).

---

## Repo layout (key dirs)
```
backend/
  main.py                      # app factory; ALL router includes; startup hooks (load_overrides_from_db ~L437)
  app/
    ai/
      agent_v2.py              # planner/execute/reflect loop (CORE — edit minimally)
      context_hub.py           # registers context builders (CORE)
      context_view.py          # exposes context sections (CORE)
      tools/
        base.py                # Tool abstract base (run_stream → ToolEvent)
        metadata.py            # ToolMetadata
        implementations/       # DROP A FILE = auto-registered internal tool (pkgutil)
        mcp/                   # MCP_TOOLS dict: create_data, create_artifact, create_report...
      context/builders/        # context builders (+ register in context_hub)
      brain/                   # 2nd-brain: distiller, knowledge_proposer, brain_graph
    data_sources/
      clients/                 # <type>_client.py per connector (BaseClient: test_connection/get_schemas/execute_query)
    models/                    # SQLAlchemy ORM (data_source, report, artifact, visualization, studio, scheduled_prompt...)
    routes/                    # FastAPI routers (one prefix each)
    services/                  # business logic (data_source_service, report_service, notification_service...)
      report_delivery/         # v1.37 clean-email engine (see below)
    schemas/
      data_source_registry.py  # 46 connectors: Config + Credentials per type
    settings/
      hybrid_flags.py          # HYBRID_* flags (property + UPGRADE_FLAGS + snapshot)
    alembic/                   # migrations (chain off TRUE single head)
frontend/
  pages/                       # routes (studios/[id]/index.vue = studio detail w/ tabs)
  components/studio/           # StudioChat/Connectors/Reports/Channels/Email/Intelligence... (one per tab)
  components/dashboard/        # ArtifactFrame.vue (sandboxed iframe render)
  composables/useAppNav.ts     # nav model (groups/tabs) — single source for TopNav + AppRail
  utils/artifactIframe.ts      # posts data into artifact iframe
folder-sync-agent/             # standalone desktop ingest agent (baked at /app/folder-sync-agent)
reference/dash/                # READ-ONLY blueprint, NOT run. Don't import.
```

---

## Extension patterns (the high-value part — how to add things fast)

### Add an agent tool (internal)
Drop `app/ai/tools/implementations/my_tool.py` with `class MyTool(Tool)` → auto-discovered by
`implementations/__init__.py` (pkgutil + issubclass). Implement `metadata` (ToolMetadata) +
`async run_stream(tool_input, runtime_ctx)` yielding `ToolStart/ToolProgress/ToolComplete/ToolError`.
`runtime_ctx` carries db/org/completion/report/user. **Must inherit `Tool` or it won't register.**
Templates: `mcp/create_data.py` (query→viz), `mcp/create_artifact.py` (vizs→dashboard/slides), `implementations/run_eval.py`.

### Add a data-source type (connector)
1. `schemas/data_source_registry.py` → `<Type>Config` + `<Type>Credentials` + registry entry.
2. `data_sources/clients/<type>_client.py` → inherit `BaseClient`, implement `test_connection`/`get_schemas`/`execute_query` (+ Capabilities).
3. File-based ingest path = `services/data_source_service.py::create_data_source_from_file`.
   ⚠️ **GREENLET LANDMINE:** that fn commits internally → expires ORM objects. Capture org_id/user_id/file_name as
   strings up-front; RE-QUERY rows fresh after ingest. Never touch expired ORM objects.

### Add a HYBRID flag (3-place or it's invisible)
`settings/hybrid_flags.py`: (1) `@property HYBRID_X`, (2) `UPGRADE_FLAGS["HYBRID_X"]={label,role,category,status,note}`,
(3) add to `snapshot()`. Default OFF. Use `from app.settings.hybrid_flags import flags; if flags.HYBRID_X:`.
ON per-org via DB `organization_settings.config.hybrid_overrides` (loaded at boot — a bare `docker exec python`
does NOT trigger that load, so flag reads there mislead). **Absent from UPGRADE_FLAGS = invisible in UI + PUT 400s.**

### Add a context builder
`ai/context/builders/X_context_builder.py` + register in `context_hub.py` + section in `context_view.py` +
inject in `agent_v2.py`. **Touches 3 CORE files** (rebase tax) — mirror the brain/knowledge path exactly.

### Add a migration
Chain off the **TRUE single head** (a revision no one lists as `down_revision`, accounting for **tuple**
down_revisions in merge migrations — naive head-finding gives false multiples). Guard PG-only DDL with
`op.get_bind().dialect.name == "postgresql"`. Flags need NO migration; new tables do. Current head `agentconn1`.

### Add a frontend studio tab
`pages/studios/[id]/index.vue`: add nav item (group + label) + `v-else-if="activeTab==='x'"` → `<StudioX/>`.
New nav GROUP → `composables/useAppNav.ts`. ⚠️ **Nuxt auto-import landmine:** a component under
`components/<dir>/X.vue` is registered as `<DirX>` UNLESS filename already starts with `<Dir>` → bare `<X>`
renders nothing. Fix = name it `DirX.vue` or explicit-import. New component not picked up until `yarn dev` restart.
FE API calls use `useMyFetch` (auto Authorization + X-Organization-Id, prepends `/api`) → use BARE paths.

---

## Routes (mounted in main.py)
Org-scoped calls need header `X-Organization-Id`. Login `POST /api/auth/jwt/login` (form `username/password`).
Key prefixes: `/api/data_sources`, `/api/reports`, `/api/knowledge`, `/api/studios/{id}/...`
(channels/smtp/scheduled-reports), `/api/organization/hybrid-flags/{env}`, `/api/changelog`, `/api/sync`,
`/api/templates`, `/api/intelligence`, `/api/ext/telegram/{studio_id}/webhook`. Report create body uses
`title` + `data_sources` (NOT name/data_source_ids — silently ignored). Completions: poll `GET /reports/{id}/completions`.

## One-click dashboard in chat (how it works today)
Agent → `create_data` (N times: prompt→SQL→Visualization/Step, result-cache aware) → `create_artifact`
(`mode="page"|"slides"`, auto-selects top-10 vizs OR explicit `viz_ids`) → `Artifact(html_content, content_json)`
→ `components/dashboard/ArtifactFrame.vue` renders sandboxed iframe (fullscreen broadcasts to 2nd iframe).
**No single "whole dashboard from one prompt" tool yet** — that's ROADMAP F01 `compose_dashboard`.

## v1.37 report_delivery (clean scheduled email)
`services/report_delivery/`: `contract.py` (FROZEN: DeliveryContext/Parts, register_renderer, async `classify`),
`extract.py` (sanitize chat → clean result), `template.py`, `assembler.py` (`build_parts`→`deliver`, per-agent SMTP,
inline-cid, ×3 DNS retry), `renderers/{result,dashboard,artifact,workflow}.py` (auto-imported). Flow:
`scheduled_prompt_service.scheduled_run_prompt` (cron, claim-once) → completion → `notification_service.send_scheduled_prompt_results`
→ (flag `HYBRID_RICH_REPORT_EMAIL`) `assembler.deliver`. SMTP precedence studio→ai_mailbox→org→global via
`email_client_resolver.resolve_outbound`. Flags `HYBRID_AGENT_REPORTS` + `HYBRID_RICH_REPORT_EMAIL`.

---

## Deploy / iterate
- **Hot backend (.py):** `docker cp <f> ca-app:/app/backend/... && docker exec ca-app /opt/venv/bin/python -m py_compile <f> && docker restart ca-app` (restart KEEPS cp'd files; `--force-recreate` REVERTS to image).
- **Hot FE:** `scripts/fe-sync.sh` (host `nuxt generate` + docker cp → `ca-app:/app/frontend/dist`, EPHEMERAL). Fast-dev = `cd frontend && DASH_BACKEND=127.0.0.1:3007 yarn dev` (:3000).
- **Durable bake:** `DOCKER_BUILDKIT=1 docker build -t cityagent-analytics:dev .` (or `scripts/build.sh` pre-pulls bases w/ retry) → `docker compose -f docker-compose.build.yaml up -d --force-recreate app`.
  🔴 **NEVER force-recreate onto a stale/un-rebuilt image** — DB ahead of image migrations = broken app. Verify the new image contains your code + migration FIRST; restore via docker cp backend + fe-sync. Build can flake at `npm install -g yarn` (env network, not code).
- **Verify:** `curl :3007/health`, check 4 delivery modes + routes, flags loaded from DB overrides.

## rtk hook noise
`rtk` mangles `ls`/`grep`/`wc`/`docker logs` → returns summarized stubs (false "empty"/"0 bytes"). Use
`rtk proxy <cmd>`, `find`, or `python3 -c` for raw output; read large files with the Read tool.

## Versioning discipline (every ship)
Bump `VERSION_HYBRID` + prepend `CHANGELOG_HYBRID.md` entry (top-level bullets = plain user copy, indented = tech).
Append dated entry to `DEVLOG.md`. Update `README.md` + this map if load-bearing paths changed. Surfaced as 🔔 What's-new bell.

---

## Top landmines (condensed — full list in CLAUDE.md)
1. Stack ONLY on `docker-compose.build.yaml`. 2. Flags UI/DB-owned — never re-add `HYBRID_*` to compose/.env.
3. Nuxt auto-import `<DirX>` prefix rule. 4. Greenlet expiry after `create_data_source_from_file` commit.
5. Alembic tuple down_revision → verify true head. 6. Never force-recreate onto stale image. 7. PG18 data dir =
`/var/lib/postgresql` (mount parent). 8. Babel pinned 7.x (artifact render). 9. LDAP login config = DB via
`get_effective_ldap_*` (NOT file). 10. Secrets Fernet-encrypted, never returned. 11. `reference/dash` = read-only, don't import.
```
