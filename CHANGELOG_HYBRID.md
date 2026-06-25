# What's new — CityAgent Analytics

Hybrid feature changelog (our additions on top of the bagofwords/Dash base). Newest first.
Format per entry: `## v<semver> — <title>  (<YYYY-MM-DD>)` followed by `-` feature bullets.
Every shipped feature bumps `VERSION_HYBRID` and adds an entry here.

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
