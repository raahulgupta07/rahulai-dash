# CityAgent Analytics

Hybrid agentic-analytics platform — a fork of **bagofwords** (rebranded **Dash**), merged with dual-schema patterns, a Karpathy-style 2nd-brain, lightweight Domain-Pack "Skills", and a per-studio **Auto-train pipeline**.

An **Agent Studio** wraps a set of pinned data sources (file uploads or warehouse connectors) into a grounded, shareable analytics agent that answers questions over your data, builds dashboards + slide decks, and trains itself — no per-dataset code.

- **Backend** — FastAPI (Python 3.11), async SQLAlchemy, Alembic migrations.
- **Frontend** — Nuxt 3 SPA (baked into the image via `nuxt generate`).
- **Data** — PostgreSQL 18 + pgvector, pgbouncer pool, Redis.
- **LLM** — **OpenRouter only** (Dash `custom` provider, per-org Fernet-encrypted key).
- **Image** — single `cityagent-analytics:dev`, served on `:3007`.

> Full engineering guide + landmines: **`CLAUDE.md`** (read it before touching anything). Dated per-feature changelog: **`DEVLOG.md`**. Architecture: `docs/ARCHITECTURE.html` · Plans: `docs/PLAN_*.md`.

---

## Prerequisites

- **Docker** + Docker Compose v2 (Desktop or engine). All services run in containers.
- **~8 GB RAM** free for the build (the Nuxt generate step needs headroom).
- An **OpenRouter API key** (https://openrouter.ai) — the only LLM provider.
- Ports free on the host: `3007` (app), `5439` (Postgres), `6432` (pgbouncer), `6399` (Redis).
- For local frontend iteration only: **Node 20+** and `npm`.

---

## Install / quick start

```bash
# 1. clone, then from the repo root:
cd "CityAgent Analytics"

# 2. build: pre-pulls base images (with retry), builds cityagent-base:dev once,
#    then the app image. ~5–10 min cold.
bash scripts/build.sh

# 3. run (the scale overlay adds Redis + pgbouncer)
docker compose -f docker-compose.build.yaml -f docker-compose.scale.yaml up -d

# 4. verify
curl localhost:3007/health        # -> {"status":"ok"}
```

Open **http://localhost:3007**.

**First user:** register at the login screen (or `POST /api/auth/register` with `{email, password, name}`). The first uninvited user auto-creates an org and becomes its admin. Set your own credentials — do **not** ship a default password.

**Ports:** app `:3007` (internal 3000) · Postgres `:5439` · pgbouncer `:6432` · Redis `:6399`.

### Seed the LLM provider (required)

The app has no LLM until you add an OpenRouter key. Either set it in `.env` (see below) before first boot, or seed it after:

```bash
docker exec ca-app python backend/scripts/seed_openrouter.py
```

This registers the `custom` (OpenRouter) provider for the org and selects default models. Without it, chat + training will fail.

---

## Configuration (`.env`)

Copy `.env.example` → `.env` and set at minimum:

| Var | What | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | your OpenRouter key | required for any LLM call |
| `DASH_SECRET_KEY` | Fernet key for encrypting per-org secrets | generate once, keep stable |
| `DATABASE_URL` | Postgres DSN | defaults wired for the bundled `ca-postgres` |
| `PUBLIC_URL` | external base URL | needed for embed/SDK + CORS in prod |
| `STUDIO_LEARN_DAEMON_ENABLED` | background self-learn daemon | leave `0` unless you want it |

> **Landmine:** a compose `${VAR:-default}` beats the in-app registry default. If a setting won't take, check the compose env first.

---

## How it works

1. **New Studio** — name + sharing (avatar/voice/summary auto-written).
2. **Add data** — open a Studio → **Auto-pilot** tab → **Add a source** (pin an org connection or create a new one across 46 connector types) **or** **Upload file** (`.csv`/`.xlsx`, multi-select supported). A connector with N tables trains every table.
3. **Auto-train everything** — one button: profile columns → extract knowledge from docs → mine joins → write example queries + eval goldens → generate 6 artifacts. Readiness climbs 0→100 in the background.
4. **Ask** — the agent answers grounded on your data, builds dashboards (React + ECharts) and slide decks (python-pptx).

A guided wizard also lives at **`/studios/new-agent`** (Name → Data → Train → Ready).

### Auto-pilot tab (the studio home)

A 3-step flow on `studios/[id]` (`activeTab='autopilot'`):

1. **Add** — two tiles. **Add a source** opens a popup picker of your **org connection library** (connections listed by name + host; Pin / ✓Pinned; search; **+ New connection** opens the shared 46-type connector modal → creates in the org → auto-pins). **Upload file** takes one or many spreadsheets off your machine (each becomes its own source and auto-pins).
2. **Route** — four lanes (**Data · Knowledge · Skill · Rule/Instruction**) show what the agent is made of, drawn from the studio's real sources / docs / instructions / examples. Pasted methods or rules go through **Teach**, which classifies them into a lane with a confidence score (re-route if wrong).
3. **Train** — one **Auto-train everything** button, disabled until ≥1 source is added.

### Connector model — one source of truth

**Org library = the single home for connections; an agent only references (pins) them.**

- **Create** a connection (any of 46 types) → it lands in the **org registry** (credentials stored once, Fernet-encrypted). The same shared modal is reachable from **Manage → Connectors** and from a Studio's **+ New connection**.
- **Manage** (edit / test / rotate creds / delete) → **Manage → Connectors** only.
- **Use** in an agent → pin from the org library; pinning scopes one connection (and a table subset) to that agent. No agent ever stores credentials.
- **N of one type** is fine: connector *type* is a template, each connection is a **named instance**. Ten Postgres = ten named rows. Blank names auto-derive `Postgres · host/db` so they stay distinct.

---

## Auto-train pipeline (per pinned source)

| Stage | What | Module |
|---|---|---|
| Profile | every column → role · distinct · sample values · null % (all tables) | `column_intel` |
| Knowledge | extract definitions from uploaded `.xlsx`/`.pptx`, applied live | auto-configure |
| Queries | LLM example SQL, **verified read-only** before saving | `auto_queries` |
| Evals | golden Q→expected from real aggregates | `auto_evals` |
| Joins | value-overlap mining (works day 1) + proven-SQL mining | `join_miner` |
| Artifacts | Summary · FAQ · Briefing · Notes · KPI pack · Data dictionary | `studio_artifacts` |

Training is **async** (`POST /studios/{id}/train`, poll `GET .../train/status`). Profiling reports **per-table progress** (the status bar moves table-by-table) and per-source has a 600 s timeout so a hung remote query fails soft instead of freezing the run. Re-trains skip unchanged tables (row-count watermark) and surface schema drift.

> When `HYBRID_SEMANTIC_LAYER` / `HYBRID_METRICS_CATALOG` are ON, **Auto-train everything** now also fills the **Semantic** + **Metrics** tabs (a `semantic_metrics` stage proposes table meanings + KPI definitions from each source schema and auto-approves them — no separate AI-suggest click needed). With the flags OFF, those tabs stay empty (opt-in). **Assets** is still opt-in. The Review queue is empty after a train because Auto-train auto-approves.

---

## Domain Packs — lightweight "Skills"

A **Domain Pack** is a declarative `.yaml` recipe in `backend/app/ai/packs/library/` (method + required inputs + output spec). It is **never executed** — the router injects its `[METHOD] + [BINDING]` into the AgentV2 planner so the stable `create_data`/`create_artifact` loop follows it.

- **3-layer gate** prevents wrong-skill firing: (1) bind gate (required inputs must map to the agent's real columns), (2) trigger gate (question must match the domain), (3) score + learned win-rate.
- **48 packs ship** — Finance (ebitda + Tier A/B/C) ported from the Anthropic financial-services method, and 33 general-analytics packs ported from the data-analytics-skills library. Packs whose columns are missing bind **dormant** until the column appears (re-checked on schema drift).
- **Teach Box** (Studio → Teach) — paste an analysis → one LLM call classifies it into `SKILL`/`INSTRUCTION`/`DATA_RULE`/`KNOWLEDGE`, each born **pending** behind the review gate.
- **Review UI** — Studio → **Skills** tab (approve/reject/promote, binding + win-rate + dormant hints); org-wide **Settings → Pack Analytics**.

Plan: `docs/PLAN_TEACH_SKILLS_ENGINE.md`.

---

## Intelligence Layer (dash-parity grounding)

Eight capabilities that close the prompt-context gap vs the `reference/dash` blueprint. All flag-gated (default OFF) and additive. Each surfaces per-agent in **Studio → Intelligence** (8 tabs), with live data + an org-wide toggle, read via `GET /api/intelligence/layer/{layer}`.

| Layer | Flag | What |
|---|---|---|
| Deep Profiler | `HYBRID_PROFILE_V2` | per-column role catalog (DIMENSION/STATE/MEASURE/IDENTIFIER/TEMPORAL) + top-3 values + variant warnings |
| Lazy Profile / Drift | `HYBRID_PROFILE_V2` | cache-miss → inline-profiles a table added after training, at query time |
| Proactive Insights | `HYBRID_PROACTIVE_INSIGHTS` | z-score + IQR + spike scan on every result → chips (no LLM, fail-soft) |
| Forecasting | `HYBRID_FORECAST` | Prophet `forecast_df` tool (lazy-import; needs an image rebuild to bake prophet) |
| Golden Queries | `HYBRID_GOLDEN_QUERIES` | promote proven SQL (👍 or verified ≥2) → injected first for reuse |
| Code Enrich | `HYBRID_CODE_ENRICH` | LLM extracts grain / formulas / population from DDL+SQL → `pipeline_logic` |
| Verified Metrics | `HYBRID_VERIFIED_METRICS` | a locked metric runs its own read-only `sql_calc`, marked AUTHORITATIVE, drift-tracked |
| Hybrid Search + KG | `HYBRID_SEMANTIC_SEARCH` | pgvector + BM25 RRF + entity graph (scaffold — no prompt injection yet) |

Migration chain: `resultcache1 → goldenq1 → verifmetric1 → hybridsearch1`. Each flag needs **both** a `@property` and an `UPGRADE_FLAGS` entry (else per-org overrides are silently ignored). The five safe layers (Profiler, Lazy, Verified Metrics, Golden, Insights) are enabled by default for the dev org; Code Enrich (per-table LLM cost), Forecast (needs prophet bake) and Hybrid Search (scaffold) stay OFF.

> Next: ingest-storage upgrade (Parquet canonical store) + LLM merge-judge for semantic same-schema detection — plan in `docs/PLAN_INGEST_STORAGE.md`.

---

## Deploy / iterate

The **frontend is baked** (`nuxt generate`) into the image. The **backend** can be hot-iterated.

```bash
# --- frontend change (.vue / nuxt config) ---
cd frontend
NODE_OPTIONS=--max-old-space-size=6144 npm run generate     # outputs to .output/public
docker cp .output/public/. ca-app:/app/frontend/dist        # no restart needed
docker commit ca-app cityagent-analytics:dev                # bake so it survives recreate

# --- backend change (.py) ---
docker cp backend/app/<file>.py ca-app:/app/backend/app/<file>.py
docker exec ca-app python -m py_compile /app/backend/app/<file>.py
docker restart ca-app
docker commit ca-app cityagent-analytics:dev
```

> **Hard rules:**
> - **Never** `docker compose ... --force-recreate` — it re-bakes from the image and wipes hot-copied files.
> - **Never** rebuild the image from disk after a hot-copy without re-baking — `docker commit` is what persists.
> - **Never** pull `bagofwords/bagofwords:latest` — always build `cityagent-analytics:dev` from this repo.
> - On macOS, `/usr/bin/ls` may be absent — use `/bin/ls`.

Per-org feature flags can be flipped live: `PUT /api/organization/hybrid-flags/{env}` body `{"enabled": true|false}` (or **Settings → Feature Flags**).

### Share an agent as a Template

A smart agent can be exported as a **Template** — its data-agnostic know-how (rules, metric formulas, example patterns, skills, persona), with data/credentials/column-names stripped. Others browse the **Templates** gallery (Studios → Templates), pick one, **bind** its required column-roles to their own columns in a wizard, and get their own agent — imported rules/metrics land *pending* for review. Export from a studio header (**Export as Template**). Versioned (`VERSION_HYBRID`-style semver), org or global scope. Flag `HYBRID_AGENT_TEMPLATES`. Reuses the Domain-Pack bind-gate + review gate. See `docs/PLAN_AGENT_TEMPLATES.md`.

### Install as an app (PWA)

The frontend is an installable PWA. In Chrome/Edge, open the app and click **Install app** in the top bar (left of the 🔔 bell) or the ⊕ in the address bar — it installs to the dock/start menu as a standalone window with an offline shell. The service worker precaches the app shell but **never caches `/api` or `/ws`** (always live data/auth). Built automatically by `@vite-pwa/nuxt` during `nuxt generate` (`sw.js` + `manifest.webmanifest`).

> **Prod requires HTTPS** for install + the service worker (set `PUBLIC_URL` to an https origin behind TLS); `http://localhost:3007` is exempt for testing. iOS uses Share → Add to Home Screen (no programmatic prompt).

### Releasing a feature (changelog)

Shipped features are versioned in `VERSION_HYBRID` (hybrid semver, e.g. `1.2.0`) with a matching entry in `CHANGELOG_HYBRID.md` (`## v<semver> — <title>  (<YYYY-MM-DD>)` + `-` bullets, newest first). The app exposes this at `GET /api/changelog` and surfaces it as a **🔔 What's new** popover in the top bar (bell before the user profile) with an unseen badge per user. Bump `VERSION_HYBRID` and prepend a `CHANGELOG_HYBRID.md` entry whenever you ship — the bell updates automatically. Full feed at `/changelog`.

---

## Feature flags

New features are flag-gated (`backend/app/settings/hybrid_flags.py`, env `HYBRID_*`, default OFF; dev `.env` turns them on). Per-org live overrides via **Settings → Feature Flags**.

Key flags: `COLUMN_INTEL · AUTO_QUERIES · AUTO_EVALS · JOIN_GRAPH · DOC_KNOWLEDGE · STUDIOS · SEMANTIC_LAYER · METRICS_CATALOG · DOMAIN_PACKS · PACK_ROUTER · PACK_AUTOBIND · TEACH_BOX · SCOPE_GATE · FOLLOWUPS`. Intelligence Layer: `PROFILE_V2 · PROACTIVE_INSIGHTS · FORECAST · GOLDEN_QUERIES · CODE_ENRICH · VERIFIED_METRICS · SEMANTIC_SEARCH`. Env knob: `STUDIO_LEARN_DAEMON_ENABLED`.

For stability, **Skills (heavy sandbox exec) / sub-agents / MCP are OFF by default**; the lightweight Domain-Pack path is the supported "skills" mechanism.

---

## Architecture rules (for contributors)

1. **OpenRouter only** for LLM (Dash `custom` provider, per-org encrypted key).
2. Touch Dash core **minimally** — prefer new files + hook points (fast-moving OSS fork).
3. Everything new is **flag-gated** (default OFF); everything learned is **review-gated** (pending → approve).
4. New routes registered in `backend/main.py`; migrations chain off the single true head; no `from __future__ import annotations` on body+permission routes.
5. **UI/UX = `DESIGN_SYSTEM.md`** (clay brand tokens, serif H1, exactly 3 button variants, 3 card types, no `gray-*`). New/edited `.vue` must conform.
6. **Agents are scoped to their data** — a scope guardrail (`HYBRID_SCOPE_GATE`, default ON) refuses off-topic questions; a studio report is locked to the studio's pinned sources.
7. **Generated slides + dashboards must stay readable** — the `create_artifact` prompts enforce a contrast contract (all text/axes/legends must contrast the chosen light/dark theme).

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `{"status":"ok"}` not returned | container still booting; `docker logs ca-app` and re-check `/health` |
| Chat/training errors immediately | no LLM provider — run `seed_openrouter.py` or set `OPENROUTER_API_KEY` |
| Auto-train bar "stuck" early | profiling a large connector takes minutes; the bar now moves per table — watch `docker logs -f ca-app 2>&1 \| grep "\[profile\]"` |
| FE change didn't show | you skipped the bake — `docker cp .output/public/. ca-app:/app/frontend/dist` then `docker commit` |
| FE change vanished after restart | a `--force-recreate` wiped the hot-copy; rebuild + re-bake |
| Setting won't take effect | a compose `${VAR:-default}` is overriding the registry default |
| Semantic/Metrics tabs empty | enable `HYBRID_SEMANTIC_LAYER` / `HYBRID_METRICS_CATALOG` then re-run **Auto-train everything** (fills + auto-approves them); flags OFF = empty by design. Assets still opt-in (AI-suggest). |

See `CLAUDE.md` for the complete codebase map + every landmine, and `DEVLOG.md` for the per-feature changelog.
