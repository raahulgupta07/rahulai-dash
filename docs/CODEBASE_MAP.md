# CODEBASE_MAP — CityAgent Analytics

> **Expert primer. Read this instead of scanning the tree.** Load-bearing 20% only: entry points,
> extension patterns, route mounts, top landmines. Auto-loaded via `@docs/CODEBASE_MAP.md` in CLAUDE.md.
> Companion: `CLAUDE.md` (rules/current state), `DEVLOG.md` (dated history), `ROADMAP.md` (forward plan),
> `docs/INGEST_BRAIN_DESIGN.md` (F09 universal-ingest design).
> **Keep current:** when a ship changes a load-bearing path/pattern, update this file (same habit as DEVLOG bump).
> Last verified: 2026-06-26 · `VERSION_HYBRID` 1.37.0 · mig head `agentconn1`.

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
