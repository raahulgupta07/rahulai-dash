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

## Two ways to install

| Way | Effort | When |
|---|---|---|
| **A. `docker pull` from GHCR** (no build) | ~5 min | normal install — pull a prebuilt image. See **`DEPLOY-GHCR.md`**. |
| **B. Build from source** (this section) | ~15–25 min first build | you want to build/modify it yourself, or no GHCR access. |

> **Quick path for most installs is A (`docker pull`)** — `DEPLOY-GHCR.md` is the OpenWebUI-style guide.
> Build-from-source (B) is below.

---

## B. Engineer quick start — build from source

**Prereqs:** Docker + Docker Compose, **≥10 GB RAM** given to Docker (the frontend `nuxt generate`
needs a 6 GB Node heap — less = OOM/exit-134), ~15 GB free disk, ports `3007`/`5439`/`6399` free.

```bash
# 1. clone
git clone git@github.com:raahulgupta07/rahulai-dash.git
cd rahulai-dash

# 2. config
cp .env.example .env
#    Edit .env and set AT LEAST:
#      DASH_ENCRYPTION_KEY  -> generate ONCE, keep stable forever (decrypts saved keys):
#         python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
#      DASH_ADMIN_EMAIL / DASH_ADMIN_PASSWORD / DASH_ADMIN_NAME  -> first-boot admin
#      APP_PORT=3007  (or any free host port) + DASH_BASE_URL=http://<host>:3007

# 3. build + run (self-contained Dockerfile; first build ~15–25 min)
bash scripts/build.sh                                   # pre-pulls bases (retry) + builds the image
docker compose -f docker-compose.build.yaml up -d
#    (or in one shot:  docker compose -f docker-compose.build.yaml up -d --build)

# 4. verify
curl http://localhost:3007/health                       # {"status":"ok"}
```

Open `http://<host>:3007`, log in with the admin you set, then **Settings → Models** and paste the
**OpenRouter API key** (it is never baked into the image).

**Rebuild after a code change:** `bash scripts/build.sh && docker compose -f docker-compose.build.yaml up -d --force-recreate app`
(code-change rebuilds are seconds–2 min thanks to the cached base + BuildKit cache mounts).

> Notes: the app listens on **3000 inside** the container — the `http://0.0.0.0:3000` log line is normal;
> you reach it on the host `APP_PORT`. Data persists in the `ca_postgres_data` / `ca_uploads` volumes
> (survives rebuilds). **Never** `docker compose down -v` — that wipes the DB. Stack runs ONLY on
> `docker-compose.build.yaml` (a plain `docker-compose.yaml` is a different project = empty DB).

---

## C. Step-by-step install (hand-edited `.env`, no scripted seds)

For an operator who edits `.env` in a text editor and runs Docker by hand.

### 1. Clone
```bash
git clone git@github.com:raahulgupta07/rahulai-dash.git
cd rahulai-dash
```

### 2. Create your `.env`
```bash
cp .env.example .env
nano .env        # or: vi .env
```

### 3. Edit only these lines in `.env` (leave everything else as-is)

| Line / key | Default | Set it to |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` |
| `APP_PORT` | `3007` | the host port for the web app (any free port) |
| `POSTGRES_PORT` | `5439` | host port for the database (change only if 5439 is busy) |
| `REDIS_PORT` | `6399` | host port for the cache (change only if 6399 is busy) |
| `DASH_BASE_URL` | `http://localhost:3007` | `http://YOUR_SERVER_IP:<APP_PORT>` — **must match APP_PORT** |
| `DASH_ENCRYPTION_KEY` | *(empty)* | **leave empty** — auto-generated + persisted on first boot |
| `DASH_ADMIN_EMAIL` | *(commented)* | remove the `#`, set e.g. `admin@cityagent.io` |
| `DASH_ADMIN_PASSWORD` | *(commented)* | remove the `#`, set a strong password |
| `DASH_ADMIN_NAME` | *(commented)* | remove the `#`, set e.g. `Administrator` |

**Ports:** only change the host (left) number — the container's internal ports (`3000` app, `5432` db, `6379` redis) are fixed and must NOT change. If you change `APP_PORT`, change `DASH_BASE_URL` to match.
**Commented lines:** a leading `#` means the line is ignored — delete the `#` to activate `DASH_ADMIN_*`.
**Encryption key:** leaving it empty is safe now — the app generates one on first boot and stores it on the durable `ca_uploads` volume, so it survives restarts/rebuilds. (For a critical prod box you may still paste a fixed key here; an explicit key always wins.)

Save in nano: `Ctrl+O`, `Enter`, `Ctrl+X`.

### 4. Pre-pull one image (prevents a build-time network flake)
```bash
docker pull docker/dockerfile:1.7
# if it errors, just run it again until it succeeds
```

### 5. Build (first time ~15–25 min)
```bash
bash scripts/build.sh
```

### 6. Start
```bash
docker compose -f docker-compose.build.yaml up -d
```

### 7. Verify
```bash
sleep 45
curl http://localhost:<APP_PORT>/health      # expect: {"status":"ok"}
```

### 8. Log in + finish in the browser
1. Open `http://YOUR_SERVER_IP:<APP_PORT>`, log in with the `DASH_ADMIN_*` you set.
2. **Settings → Models** → paste the **OpenRouter API key** (required; nothing AI works without it).
3. **Settings → Feature Flags** → enable `HYBRID_USER_GROUPS`, `HYBRID_GROUP_ACCESS`, `HYBRID_STUDIOS` (+ any Intelligence flags).

### Everyday commands
```bash
docker compose -f docker-compose.build.yaml ps              # status
docker compose -f docker-compose.build.yaml logs -f app     # logs
docker compose -f docker-compose.build.yaml stop            # stop (keeps data)
docker compose -f docker-compose.build.yaml up -d           # start

# update to newer code later:
git pull && bash scripts/build.sh
docker compose -f docker-compose.build.yaml up -d --force-recreate app
```

### Two rules — never break
1. Always pass `-f docker-compose.build.yaml` on every command (a plain `docker compose up` = different project = empty DB).
2. **Never** `docker compose down -v` — the `-v` deletes the database volume (all data gone).

---

## Deploy

Clean machine, no pre-step, no external image — the runtime base is folded into
the `Dockerfile`, so the build is fully self-contained.

### Choose ONE deploy mode

| Mode | Compose file | Port var | Proxy | Use when |
|---|---|---|---|---|
| **Direct** (simplest) | `docker-compose.build.yaml` | `APP_PORT` | none — app published straight to host | internal / behind an existing host proxy |
| **nginx** | `docker-compose.nginx.yaml` | `HTTP_PORT` | nginx fronts the app (SSE/websocket/large-upload tuned) | you already run nginx, want a clean reverse proxy |
| **Caddy (HTTPS)** | `docker-compose.yaml` | `APP_PORT` | Caddy, auto-TLS | public domain, want automatic HTTPS |

> Pick the var that matches the mode. **Direct/Caddy use `APP_PORT`; nginx uses `HTTP_PORT`.** Setting the wrong one does nothing. Only ONE mode runs at a time — `docker compose down` the old one before switching (never `-v`, that wipes the DB).

### Direct (no proxy)

```bash
cp .env.example .env                 # then edit .env (see below)
# set APP_PORT to any FREE host port (e.g. 8001) + DASH_BASE_URL=http://<host>:8001
docker compose -f docker-compose.build.yaml up -d --build
docker compose -f docker-compose.build.yaml ps      # APP shows 0.0.0.0:<APP_PORT>->3000
curl http://localhost:<APP_PORT>/health
```

### nginx (reverse proxy)

```bash
cp .env.example .env
# set HTTP_PORT to a FREE host port (e.g. 8001) + DASH_BASE_URL=http://<host>:8001
docker compose -f docker-compose.nginx.yaml up -d --build
docker compose -f docker-compose.nginx.yaml ps      # dash-nginx shows 0.0.0.0:<HTTP_PORT>->80
curl http://localhost:<HTTP_PORT>/health
```

The app container always listens on **3000 internally** (the `http://0.0.0.0:3000`
line in the logs is normal — ignore it). The host port you reach it on is whatever
`APP_PORT`/`HTTP_PORT` you set. **"port already in use"** = another process owns that
port — pick a different free one (`ss -ltnp | grep <port>` to check).

That's the whole deploy. The first build takes ~5–20 min; rebuilds are fast.

**Optional convenience:** `bash deploy.sh` runs `docker compose up -d --build`
(Caddy mode), but first verifies Docker is up, creates `.env` from the template on
first run (and stops so you can fill it in), and warns if `DASH_ENCRYPTION_KEY` is
empty. Use it or skip it — same result.

Edit these in `.env` before deploying:

- `DASH_ENCRYPTION_KEY` — Fernet key (44 chars). Generate:
  `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `DASH_ADMIN_EMAIL` / `DASH_ADMIN_PASSWORD` — these create the **first owner
  account automatically** on first boot.

After it's up, set your **OpenRouter API key** in Settings → Models (it is never
stored in the repo or `.env`).

> First build can take ~5–20 min (runtime base apt layer + Nuxt `generate`
> compile). Subsequent rebuilds are seconds-to-minutes thanks to cached
> BuildKit stages + vendored deps.

---

## Prerequisites

- **Docker** + Docker Compose v2 (Desktop or engine). All services run in containers.
- **~8 GB RAM** free for the build (the Nuxt generate step needs headroom).
- An **OpenRouter API key** (https://openrouter.ai) — the only LLM provider.
- A free host port for the app (`APP_PORT`/`HTTP_PORT`, default `3007`/`8001` — change if taken). Plus `5439` (Postgres), `6399` (Redis) for the build stack.
- For local frontend iteration only: **Node 20+** and `npm`.

---

## Install / quick start

The build is **self-contained** — no separate base-image step. On a clean machine:

```bash
# 1. clone, then from the repo root:
cd "CityAgent Analytics"

# 2. create your .env from the template, then edit it (see Configuration below)
cp .env.example .env
#    set at least: DASH_ENCRYPTION_KEY, DASH_ADMIN_EMAIL, DASH_ADMIN_PASSWORD

# 3. build + run everything (first cold build ~5–20 min; rebuilds are fast)
bash deploy.sh
#    or directly:  docker compose up -d --build

# 4. verify
curl localhost:3007/health        # -> {"status":"ok"}
```

Open **http://localhost:3007**.

**First user / admin:** set `DASH_ADMIN_EMAIL` + `DASH_ADMIN_PASSWORD` in `.env` *before* the first boot — the container auto-creates the owner/admin account (idempotent: ignored once any user exists). No sign-up link is shown in the UI. Fallback if you didn't set the env vars: `POST /api/auth/register` with `{email, password, name}` (the first user always becomes org owner).

**LLM:** nothing to seed. A new org is auto-provisioned with an editable **OpenRouter** provider + the current model set. Just paste your OpenRouter key once in **Settings → Models** (it is stored encrypted per-org in the DB — never in the repo or `.env`).

**Ports:** app `:3007` (internal 3000) · Postgres `:5439` · pgbouncer `:6432` · Redis `:6399`.

> Optional scale overlay (extra Redis + pgbouncer tuning): `docker compose -f docker-compose.yaml -f docker-compose.scale.yaml up -d`.

---

## Configuration (`.env`)

Copy `.env.example` → `.env`. The keys that matter most:

| Var | What | Notes |
|---|---|---|
| `DASH_ENCRYPTION_KEY` | Fernet key encrypting per-org secrets (LLM/SMTP) | **required**; generate once, keep stable (rotating it makes stored secrets undecryptable). `python -c "import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |
| `DASH_ADMIN_EMAIL` / `DASH_ADMIN_PASSWORD` | bootstrap the first owner/admin | set once for a fresh deploy; idempotent — ignored if any user exists |
| `APP_PORT` | host port for **direct / Caddy** modes | maps `<APP_PORT>` → container 3000; pick a free port. Ignored by nginx mode. |
| `HTTP_PORT` | host port for **nginx** mode | nginx publishes this → proxies to app:3000. Ignored by direct/Caddy modes. |
| `DASH_DATABASE_URL` | Postgres DSN | defaults wired for the bundled `ca-postgres`; override for an external DB |
| `DASH_BASE_URL` | external base URL | needed for embed/SDK + CORS + channel webhooks in prod; **set to match your published port/domain** |
| `ENVIRONMENT` | `development` \| `production` | compose sets `production` |

The **OpenRouter LLM key is NOT an env var** — it is entered from the UI (Settings → Models) and stored encrypted per-org.

> **Landmine:** a compose `${VAR:-default}` beats the in-app registry default. If a setting won't take, check the compose env first.

---

## Install & update

The stack is **one image** built from this repo — `cityagent-analytics:dev` — run via **`docker-compose.build.yaml`** (the only supported compose file; the plain `docker-compose.yaml` is a different project = empty DB). Schema migrations + the compiled front-end bundle are baked into the image and applied on boot.

### Fresh installation (from zero)

**Prerequisites:** Docker + Docker Compose; give Docker **≥10 GB RAM** for the first build (the `nuxt generate` front-end stage forces a 6 GB Node heap); git. First-ever build (base image + app) is ~20 min; later code-change rebuilds are seconds–2 min (BuildKit cache + vendored deps).

```bash
# 1. Get the code
git clone <repo> && cd "CityAgent Analytics"

# 2. Create .env from the template
cp .env.example .env

# 3. (OPTIONAL) Fernet encryption key — encrypts every stored OpenRouter/SMTP secret.
#   You can SKIP this: if DASH_ENCRYPTION_KEY is empty, start.sh auto-generates one on first
#   boot and persists it to the durable ca_uploads volume (/app/backend/uploads/.dash_encryption.key),
#   so it stays stable across restarts/rebuilds. Set it explicitly ONLY if you need a known key
#   (multi-host, or restoring a DB dump taken on another box):
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   -> paste into .env as:  DASH_ENCRYPTION_KEY=<that value>   (KEEP IT FOREVER — changing it orphans all secrets)
#   ⚠ Don't `docker compose down -v` — that drops the volume holding the auto-generated key.

# 4. (optional) edit .env:
#    APP_PORT=3007 / POSTGRES_PORT=5439 / REDIS_PORT=6399   (host ports)
#    DASH_BASE_URL=http://localhost:3007                    (MUST match your published port/domain)
#    DASH_ADMIN_EMAIL / DASH_ADMIN_PASSWORD / DASH_ADMIN_NAME  (headless super-admin seed)
#    OPENROUTER_API_KEY=sk-or-...                           (auto-lights the seeded models; else set it in the UI later)

# 5. Build the image (pre-pulls base images with retry, builds cityagent-analytics:dev)
bash scripts/build.sh

# 6. Start the stack (Postgres 18 + Redis + app; runs `alembic upgrade head` on boot)
docker compose -f docker-compose.build.yaml up -d

# 7. Verify
curl localhost:3007/health                               # -> {"status":"ok"}
docker compose -f docker-compose.build.yaml logs -f ca-app   # watch: migrations + "Loaded N hybrid flag override(s)"
```

**First sign-in** — open **http://localhost:3007**:
- If you set `DASH_ADMIN_*` in `.env`, that super-admin is seeded on boot — just log in.
- Otherwise the sign-in page shows a **"Create super-admin"** form (zero-user install); the first user created becomes the global super-admin + org owner. Sign-up then locks.

**Make the agent answer** — set the LLM key (OpenRouter only):
- If you put `OPENROUTER_API_KEY` in `.env`, the 5 seeded models light up automatically.
- Otherwise go to **Settings → Models**, paste your OpenRouter key into the seeded provider, and the preset models enable.

**Add data to try it** — open a Studio → **Auto-pilot → Upload file** (`.csv`/`.xlsx`) or pin a connector; or load the built-in Chinook demo (`POST /api/data_sources/demos/chinook`). Then ask a question in chat.

### Update to a new version

Two lanes — pick by what changed.

**A · Full rebuild (clean, durable — production):**
```bash
git pull
bash scripts/build.sh                                              # rebuild image (BuildKit cache; secs–2min if only code changed)
docker compose -f docker-compose.build.yaml up -d --force-recreate # recreate; `alembic upgrade head` runs on boot
docker compose -f docker-compose.build.yaml logs -f ca-app         # watch: migrations + "Loaded N hybrid flag override(s)"
```
🔴 **Never `--force-recreate` onto a stale/un-rebuilt image** — DB ahead of image migrations = broken app. Rebuild first, or use lane B.

**B · Hot update + bake (fast dev iteration, no full rebuild):**
```bash
# front-end change:
bash scripts/fe-sync.sh                                            # nuxt generate + docker cp -> ca-app:/app/frontend/dist (live, no restart)

# back-end change (.py):
docker cp <file> ca-app:/app/backend/app/...
docker exec ca-app /opt/venv/bin/python -m py_compile /app/backend/app/...   # verify
docker restart ca-app                                             # restart KEEPS cp'd files (force-recreate REVERTS to image)

# make it durable (so a force-recreate keeps it):
docker cp VERSION_HYBRID        ca-app:/app/VERSION_HYBRID         # version files are read per-request (What's-new bell)
docker cp CHANGELOG_HYBRID.md   ca-app:/app/CHANGELOG_HYBRID.md
docker commit ca-app cityagent-analytics:dev                      # bake the running container into the image
docker tag    cityagent-analytics:dev cityagent-analytics:v1.59.0 # version tag = rollback point
```

### Notes
- **Migrations run automatically** in `start.sh` (`alembic upgrade head`, retried) before uvicorn — no manual step. Current head: **`connvis1`**.
- **Every shipped change bumps `VERSION_HYBRID`** + prepends a `CHANGELOG_HYBRID.md` entry (surfaced as the 🔔 What's-new bell). These two files are read from the container per-request — `fe-sync.sh` does **not** copy them, so `docker cp` both on every version bump (lane B) or rebuild (lane A bakes them).
- **Back up Postgres first** on a real deploy: `docker exec ca-postgres pg_dump -U dash dash > backup_$(date +%F).sql`. **Never `docker compose down -v`** (drops the volume).
- **Keep `DASH_ENCRYPTION_KEY` unchanged** across updates — a new key orphans every stored OpenRouter/SMTP secret (Fernet).
- **New feature flags default OFF.** Enable per-org from **Settings → Feature Flags** (writes `organization_settings.config.hybrid_overrides`), then **`docker restart ca-app`** — the app runs `--workers 4`, so one restart is needed to converge a flag change across all workers.
- **Roll back:** `docker tag cityagent-analytics:v<prev> cityagent-analytics:dev && docker compose -f docker-compose.build.yaml up -d --force-recreate ca-app` (versioned image tags are your rollback points). Alembic downgrades are not guaranteed — restore the DB dump if a migration must be reversed.

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

### Connector model — owned connections with 3-level visibility

**Every connection has an owner (its creator) and a visibility; an agent only references (pins) connections.** The **Connectors** page (`Manage → Connectors`) is open to **all members** and lists, as a table, the connections you created + ones shared to you + org-wide ones.

- **Create** a connection (any of 46 types) → it lands in the org with `owner_user_id = you` and **visibility `private`** by default (credentials stored once, Fernet-encrypted). The shared modal is reachable from **Manage → Connectors** and a Studio's **+ New connection**.
- **Share** from the table — a per-row badge (🔒 Private / 👥 Shared / 🌐 Org-wide) opens a sharing panel:
  - **Private** — only you (the owner) and super admins.
  - **Shared** — you + specific users/groups you grant (writes `resource_grants`).
  - **Org-wide** — every member of the org. Self-service, no admin approval (audit-logged).
- **Manage** (edit / test / rotate creds / delete) → the **owner** of a connection, or any **super admin** (full override, incl. others' private connections). Credentials are never returned to the browser. Authz is enforced by a single `guard_owned_connection` dependency on every connector mutate route.
- **Use** in an agent → pin a connection you can see; pinning scopes it (and a table subset) to that agent. Queries run under the connection's `auth_policy` (e.g. `system_only`) so a member can query a shared connection's data without ever seeing its credentials. No agent stores credentials.
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

> **Prod requires HTTPS** for install + the service worker (set `base_url` in `dash-config.yaml` to an https origin behind TLS); `http://localhost:3007` is exempt for testing. iOS uses Share → Add to Home Screen (no programmatic prompt).

### Folder Sync — auto-ingest a local folder ("like Claude Code")

Point a small desktop app at a folder; new and changed **Excel/CSV** files become data agents automatically — no clicks. A browser can't watch the local filesystem, so this is a tiny background helper (`folder-sync-agent/`) that pairs with a one-time **sync key** and pushes only deltas.

- **Pairing** — Settings → **Folder Sync** (or any studio's **Add data → Sync a folder ⟳**) generates a `bow_` API key. Paste it + the server URL into the desktop app.
- **Per-agent binding** — a folder syncs into a specific agent; the tray app picks which one (or “new agent from folder”).
- **Smart deltas** — a local `sha256` ledger means byte-identical files are skipped without a network call; an edited file with the same schema **replaces the same agent** (no duplicates, via the existing content-hash dedup + same-schema merge); deletes are ignored.
- **Server** — `POST /api/sync/file` (multipart + `X-API-Key`), plus `/api/sync/status`, `/api/sync/agents`, `/api/sync/key`. Auth reuses `mcp_auth` (JWT or API key) so the agent runs headless. State lives in `folder_sync_states` (path → last hash → resolved DataSource/Studio); no file bytes are stored there.
- **Desktop app** — `folder-sync-agent/sync_agent.py` (stdlib + `requests` + `watchdog`; `setup`/`run`/`status`/`agents` CLI; config + state in `~/.cityagent-sync/`) plus an optional `pystray` tray (`tray.py`). The modal's **macOS / Windows / Linux** buttons download it as a zip via `GET /api/sync/download/{os}` (the agent source + a per-OS `INSTALL.txt`); then `pip install -r requirements.txt && python sync_agent.py setup && python sync_agent.py run`. Signed native installers are Phase 6. **Note:** the agent source must be baked into the image at `/app/folder-sync-agent` (a fresh `docker build` needs a Dockerfile `COPY`, else the download returns 503).

Flag `HYBRID_FOLDER_SYNC` (default OFF).

### Scheduled Reports — agent emails a clean result on a cadence

Any studio can email a **structured result** (not the raw agent chat) on a cron schedule. Studio → **Manage → Reports**: create/edit/pause/delete a scheduled prompt, set cadence + subscribers + a **format** (`auto · table · dashboard · artifact · workflow`), and **Send test now**. On each run the agent executes against a hidden per-studio container report, the result is rendered **clean** (zebra table / Playwright dashboard PNG+PDF / artifact preview / workflow timeline), and is delivered via the **agent's own SMTP identity** (per-studio → AI-mailbox → org → global).

- **Engine** — `backend/app/services/report_delivery/` (frozen `contract.py` + auto-discovered `renderers/<mode>.py`; sanitizer strips planning/fences/recap noise). Per-agent SMTP via `email_client_resolver.resolve_outbound(...)`. Routes `routes/studio_reports.py`; UI `components/studio/StudioReports.vue`.
- **Flags** — `HYBRID_AGENT_REPORTS` (Reports tab) + `HYBRID_RICH_REPORT_EMAIL` (rich-render engine; OFF = legacy raw path). Both default OFF.
- **Note** — dashboard/artifact rendering needs the image's headless chromium (Playwright) + `soffice`/`pdftoppm`; transient Docker-DNS SMTP failures are retried ×3.

### One-click artifacts — Dashboard / Slides / Excel from a report's charts

When a report already has charts, its right-panel **Dashboard**, **Slides** and **Excel** views turn their empty states into one-click builders (no chatting):

- **Generate dashboard** — builds a real interactive **page** artifact (KPI cards + responsive chart grid); rendered by `ArtifactFrame`.
- **Generate slide deck** — builds a real **slides** artifact: a python-pptx deck with native charts + page previews, **exportable to `.pptx`** (replaces the lightweight client-side placeholder deck).
- **Excel auto-fills** — one sheet per chart, populated with the real query grids.

Each builder reuses the chat `create_artifact` pipeline over the report's existing visualizations (no new analysis), so the output is identical to one the agent would make in chat.

- **Backend** — `routes/report_slides.py`: `POST /api/reports/{id}/dashboard/generate` (mode=`page`) + `…/slides/generate` (mode=`slides`) share `_generate_artifact(mode)`; read-only `GET /api/reports/{id}/workbook` returns the Excel sheets from each query's latest success step (`steps.data`, parquet-hydrated, capped 5000 rows × 50 sheets). Slides need headless `soffice`/`pdftoppm` for previews.
- **Flag** — `HYBRID_ONECLICK_ARTIFACTS` (default OFF). Flag OFF = legacy empty states / client `SlidesPanel`.

### Releasing a feature (changelog)

Shipped features are versioned in `VERSION_HYBRID` (hybrid semver, e.g. `1.2.0`) with a matching entry in `CHANGELOG_HYBRID.md` (`## v<semver> — <title>  (<YYYY-MM-DD>)` + `-` bullets, newest first). The app exposes this at `GET /api/changelog` and surfaces it as a **🔔 What's new** popover in the top bar (bell before the user profile) with an unseen badge per user. Bump `VERSION_HYBRID` and prepend a `CHANGELOG_HYBRID.md` entry whenever you ship — the bell updates automatically. Full feed at `/changelog`.

---

## Feature flags

New features are flag-gated (`backend/app/settings/hybrid_flags.py`, env `HYBRID_*`, default OFF; dev `.env` turns them on). Per-org live overrides via **Settings → Feature Flags**.

Key flags: `COLUMN_INTEL · AUTO_QUERIES · AUTO_EVALS · JOIN_GRAPH · DOC_KNOWLEDGE · STUDIOS · SEMANTIC_LAYER · METRICS_CATALOG · DOMAIN_PACKS · PACK_ROUTER · PACK_AUTOBIND · TEACH_BOX · SCOPE_GATE · FOLLOWUPS · AGENT_TEMPLATES · FOLDER_SYNC · AGENT_REPORTS · RICH_REPORT_EMAIL · ONECLICK_ARTIFACTS · GROUP_ACCESS · USER_GROUPS`. Intelligence Layer: `PROFILE_V2 · PROACTIVE_INSIGHTS · FORECAST · GOLDEN_QUERIES · CODE_ENRICH · VERIFIED_METRICS · SEMANTIC_SEARCH`. Env knob: `STUDIO_LEARN_DAEMON_ENABLED`.

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
| Chat/training errors immediately (401) | no OpenRouter key yet — paste it in **Settings → Models** (the provider is auto-seeded; the key is stored encrypted per-org, not in `.env`) |
| `cityagent-base:dev pull access denied` on build | old/stale build invocation — the base is now folded into the Dockerfile; just `docker compose up -d --build` (or `bash deploy.sh`) |
| `bind: address already in use` / `port is already allocated` | another process owns that host port — `ss -ltnp \| grep <port>` to find it, then set a free `APP_PORT` (direct/Caddy) or `HTTP_PORT` (nginx) in `.env`. The app needs only ONE free host port; its other app can keep theirs. |
| Logs say `http://0.0.0.0:3000` but you set another port | that line is the **container-internal** port (always 3000) — normal. Your real port is the `0.0.0.0:<port>->...` in `docker compose ps`. |
| `port already in use` only when switching proxy modes | the old stack is still running — `docker compose -f <old-file> down` (no `-v`) before `up` on the new compose file. |
| Hot-copy to `ca-app:/app/frontend/dist` → Permission denied | `dist` is root-owned — use `docker exec -u 0 ca-app` for the `rm`/`mkdir`, copy, then `chown -R app:app /app/frontend/dist` |
| Auto-train bar "stuck" early | profiling a large connector takes minutes; the bar now moves per table — watch `docker logs -f ca-app 2>&1 \| grep "\[profile\]"` |
| FE change didn't show | you skipped the bake — `docker cp .output/public/. ca-app:/app/frontend/dist` then `docker commit` |
| FE change vanished after restart | a `--force-recreate` wiped the hot-copy; rebuild + re-bake |
| Setting won't take effect | a compose `${VAR:-default}` is overriding the registry default |
| Semantic/Metrics tabs empty | enable `HYBRID_SEMANTIC_LAYER` / `HYBRID_METRICS_CATALOG` then re-run **Auto-train everything** (fills + auto-approves them); flags OFF = empty by design. Assets still opt-in (AI-suggest). |

See `CLAUDE.md` for the complete codebase map + every landmine, and `DEVLOG.md` for the per-feature changelog.
