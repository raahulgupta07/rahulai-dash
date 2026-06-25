# What's new — CityAgent Analytics

Hybrid feature changelog (our additions on top of the bagofwords/Dash base). Newest first.
Format per entry: `## v<semver> — <title>  (<YYYY-MM-DD>)` followed by `-` feature bullets.
Every shipped feature bumps `VERSION_HYBRID` and adds an entry here.

## v1.11.0 — One-command deploy + env super-admin  (2026-06-25)
- `docker compose up -d --build` now works on a clean machine with no pre-step — the runtime base image is folded into the main Dockerfile (no more "cityagent-base:dev pull access denied")
- New `deploy.sh`: one friendly command — bootstraps `.env` from the template, warns on a missing encryption key, then builds and starts everything
- Create the first owner/admin straight from env: set `DASH_ADMIN_EMAIL` + `DASH_ADMIN_PASSWORD` and a fresh deploy seeds the account automatically (idempotent — ignored once any user exists), no sign-up link or curl needed
- `.env.example` + `docker-compose.yaml` document the new admin vars; README/DEPLOY gained a one-command deploy section

## v1.10.0 — Per-agent access control + Telegram channels  (2026-06-25)
- Each agent (Studio) gets an "Access & Channels" settings tab
- Who-can-use: Master (whole org), Scoped (pick specific users/roles) or Link — enforced at chat time, not just in listings (flag HYBRID_AGENT_ACL)
- Per-agent model override: an agent can pin its own model (e.g. Opus) — precedence: request model > agent model > org default
- Per-agent Telegram channel: give an agent its own Telegram bot; only verified members can use it (or open to anyone), each bot is bound to exactly one agent (flag HYBRID_AGENT_CHANNELS)
- Reuses existing per-agent data connections + credential modes (shared vs per-user) so each agent stays data-isolated
- Both features default OFF — behaviour unchanged until enabled per org

## v1.9.0 — Default OpenRouter LLM + .env.example  (2026-06-25)
- New organizations are seeded with a ready OpenRouter provider and the current model set (Claude Sonnet 4.6 default, Claude Haiku 4.5 fast/small, plus Claude Opus 4.8, GPT-5.4 Mini, Gemini 2.5 Flash) — no manual provider setup
- The OpenRouter API key is left blank and entered from the UI (Settings → Models) — never stored in the repo or config; the seeded provider is editable (non-preset)
- Config-driven: `default_llm` block in dash-config supports `provider_type`, `additional_config` (base_url/verify_ssl) and `is_preset:false` for an editable, key-from-UI provider
- A blank key encrypts to a valid blob, so the model is listed and fails with a clear 401 until a real key is set — no decrypt crash
- Added a root `.env.example` documenting every environment variable (DB, encryption key, SSO, SMTP, license, ops) with placeholders only

## v1.8.0 — Rebrand to City Agent Insights  (2026-06-25)
- New CityAgent Insights logo across the app — top nav, home page and the sign-in page
- Renamed "City Agent DASH" → "City Agent Insights" everywhere (default analyst name too)
- Sign-in page cleaned up: removed the sign-up link
- LDAP is now enabled by default in org settings

## v1.7.0 — Slide workspace: Open a deck to edit & analyze  (2026-06-25)
- "Open" on a presentation now opens a clean slide workspace — the deck big on the left, a chat on the right
- The right chat is framed for slides ("Edit & analyze slides") — ask it to edit a slide or analyze the deck
- The cluttered panel tabs are hidden in this mode — just the deck
- Expand a slide to true fullscreen (Esc to exit); slide navigation stays usable
- Empty decks show a clear "No slides yet — generate a deck" instead of a blank panel
- Clearer list buttons: Open (slide workspace) vs Open in chat (the conversation); 0-slide decks say "Open & generate"

## v1.6.0 — Upload a whole folder at once  (2026-06-25)
- New "Upload a whole folder" button in the file-upload modal — picks every Excel/CSV inside a folder in one go
- Each spreadsheet becomes its own data agent (Office lock files and non-spreadsheets are skipped)
- One-shot from the browser — no desktop app needed (for continuous auto-sync, use Folder Sync ⟳)

## v1.5.1 — Folder Sync: working download buttons  (2026-06-25)
- The macOS / Windows / Linux buttons now actually download the sync app (a small Python program) as a zip
- Each download includes an INSTALL.txt with the exact setup commands for that OS
- (Signed native installers still to come — for now: pip install + python sync_agent.py)

## v1.5.0 — Folder Sync: a local folder, like Claude Code  (2026-06-25)
- Desktop sync app: point it at a folder and new/changed Excel & CSV files become data agents automatically — no clicks
- Per-agent binding: a folder syncs into a specific agent; the tray app picks which one
- Smart deltas: byte-identical files are skipped, edited files replace the same agent (no duplicates), deletes are ignored
- API-key auth: the headless agent pairs with a one-time sync key — generate it from Settings → Folder Sync or any agent's "Add data → Sync a folder"
- Connected-machines view: see every machine, its folder→agent mappings, file counts and last sync time
- Off by default (HYBRID_FOLDER_SYNC) — turn it on per org

## v1.4.2 — Clearer Agent Studios page  (2026-06-25)
- One "New Agent Studio" button (removed the duplicate add card)
- Lifecycle status on every card: Draft → Ready → Live → Idle
- Agents with no data now clearly say "needs data" with an Add-data button
- Cleaner cards — real stats only once they exist, no rows of zeros

## v1.4.1 — Smoother "Use template" journey  (2026-06-25)
- Use template now opens a guided popup (preview → data → map → review → build) instead of a page jump
- Three ways to add data: use an existing source, connect/upload new, or skip and add it later
- Skip builds the agent with the playbook now; bind columns when your data arrives

## v1.4.0 — Agent Templates: share an agent's best practices  (2026-06-25)
- Export a smart agent as a portable, versioned Template — rules, metric formulas, example patterns, skills and persona, with data and credentials stripped
- Template Gallery: browse Org and Global templates and reuse them
- Bind wizard: map a template's required columns to your own data, then build your own agent
- Imported rules and metrics land pending for review — never auto-applied

## v1.3.0 — Install as an app  (2026-06-25)
- Installable PWA: add CityAgent to your desktop or home screen as a standalone app
- One-click "Install app" button in the top bar (next to notifications)
- Offline app shell — the interface loads even on a flaky connection
- Auto-update: the app refreshes to the latest version on its own

## v1.2.0 — Intelligence Layer — 8 agent grounding capabilities  (2026-06-25)
- Deep Profiler: per-column role catalog (dimension / measure / identifier / temporal) plus value distribution and variant warnings
- Verified Metrics: locked, authoritative metric values that override improvised formulas
- Golden Queries: proven SQL is promoted and reused first
- Proactive Insights: anomaly and trend chips surfaced on every result
- Lazy Profile: tables added after training are profiled inline at query time
- Studio Intelligence rail: a new per-agent panel to view and toggle all eight capabilities
- "What's new" notifications: a release feed in the top bar with a version chip

## v1.1.0 — Studios, Auto-train pipeline & Domain Packs  (2026-06-23)
- Agent Studios: wrap pinned data sources into a grounded, shareable analytics agent
- Auto-train everything: one button to profile columns, mine joins, write example queries and generate artifacts
- Domain Packs: 48 lightweight skill recipes that steer the planner without executing code
- Teach Box: paste an analysis and have it classified into a skill, instruction, data rule or knowledge
- Auto-pilot studio home: add a source or upload files, then train in three steps
- BI dashboards: cross-filtering, conditional formatting, KPI cards and data bars

## v1.0.0 — Hybrid brain foundation  (2026-06-18)
- OpenRouter-only LLM wiring (per-org Fernet-encrypted key)
- Knowledge Layer: semantic model, metrics catalog and query library with an approval gate
- 2nd-brain learning: self-distillation from feedback, query cache and a serving funnel
- Self-service Skills with progressive disclosure and promote-from-chat authoring
- Answer cache and verified-metric grounding for faster, more reliable answers
