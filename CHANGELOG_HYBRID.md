# What's new — CityAgent Analytics

Hybrid feature changelog (our additions on top of the bagofwords/Dash base). Newest first.
Format per entry: `## v<semver> — <title>  (<YYYY-MM-DD>)` then bullets.
Bullet rules (this is the user-facing "What's new" feed):
  - **Top-level** `- ` bullets are USER-FACING — plain language, no file paths / jargon / markdown.
    These show in the in-app "What's new" popover.
  - **Indented** `  - ` bullets are TECHNICAL detail — file paths, flags, internals.
    Hidden from the popover; shown collapsed on the full /changelog page only.
Every shipped feature bumps `VERSION_HYBRID` and adds an entry here.

## v1.59.0 — Session Summary works + "forming the decision" live status  (2026-06-28)
- **Generate summary** now works — the Outputs "Session Summary" card builds a synthesis across every turn.
- While the agent forms the DECISION after an answer, a live status shows at the bottom of the chat input
  ("Reading the result… forming the decision") so you know it's still working.
  - Session Summary was never wired: `reports/[id]/index.vue` mounted `<ChatSummary>` without the
    `sessionSummary` / `sessionSummaryStale` / `sessionSummaryLoading` props or the `@refreshSessionSummary`
    handler. Added refs + `loadSessionSummary()` (GET) + `onRefreshSessionSummary()` (POST
    `reports/{id}/session-summary`) + both mounts now pass all 4. Backend route + builder already worked.
  - Decision strip: handle SSE `sense_making.pending` → `decisionForming=true`; clear on
    `completion.finished` / `completion.error`. Composer dock strip gate `autoBuilding || decisionForming`
    with dynamic label; reused existing `.cai-wave` + `.cc-shimmer`. Also pass `:senseMakingPending` +
    `:senseMaking="latestSenseMaking"` to ChatSummary so the Outputs DECISION skeleton shows too.
  - `session_summary.py` `generated_from` now also emits `turn_count` (alias of `completion_count`) so the
    card's scope sub-header populates.

## v1.58.4 — Stop auto-dashboards + DECISION on small comparisons  (2026-06-28)
- The agent no longer auto-builds a dashboard after a plain data question — you only get one when you ask.
- The DECISION card now shows on small side-by-side comparisons (e.g. 2 sites), not just big datasets.
  - `HYBRID_AUTO_ARTIFACT` turned OFF for org (DB override). `schedule_auto_artifact` was firing on every
    data turn → unrequested "Generating dashboard… 6 widgets". Reversible: flip the override back to true.
  - `sense_maker.py:410-413` skip gate loosened: was `len(signals)==0 and all df < 5 rows → None` (killed
    2-row comparisons before the LLM call). Now skips only `len(signals)==0 and all df ≤ 1 row` (true scalars).
    A 2+ row numeric comparison now reaches the LLM + grounding → DECISION card builds.

## v1.58.3 — Fix: the DECISION card is back (chat + Outputs)  (2026-06-28)
- The **DECISION** summary card now shows again under each answer in the chat — and in the Outputs panel.
- It went missing when the chat view was rebuilt; the data was there, the card just wasn't being drawn.
  - ROOT CAUSE: `sense_making` (and `auto_model`) come back as **top-level** completion fields (the
    `completion` JSON field itself is null). The message-build in `reports/[id]/index.vue` only copied
    `completion` → both fields were dropped → OutputsFeed `sys.sense_making` undefined → no DECISION
    anywhere; and the rewritten chat thread (off `CompletionMessageComponent`) never re-mounted DecisionCard.
  - FIX: carry `sense_making` + `auto_model` in BOTH message-build returns; import + mount `<DecisionCard
    :sense="m.sense_making">` inline after the answer (gated `role==='system' && !in_progress`).
  - NOTE: still data-gated — `sense_maker` returns null when no finding grounds against the rows
    (`sense_maker.py` grounding filter); clarify/inspect-only turns produce no card by design.

## v1.58.2 — Fix: Outputs panel said "No items yet" despite built dashboards  (2026-06-28)
- **Your dashboards and slides now show up in the Outputs panel.** Reports that had already built a dashboard or deck were wrongly showing "No items yet" — they now list every turn's answer, decision and artifact again.
  - Root cause: the per-turn `OutputsFeed` builds its turns from the chat `messages`, but NEITHER `ChatSummary` mount (mobile + desktop) in `pages/reports/[id]/index.vue` passed `:messages` — so the feed always had 0 turns and showed the empty state, even when `/artifacts/report/{id}` returned completed `page`/`slides` artifacts (artifacts only render inside a turn block). Added `:messages="messages"` to both mounts. (`ChatSummary` already declared the prop and forwarded it to `OutputsFeed`.)

## v1.58.1 — One thinking indicator, bigger Claude-style wave  (2026-06-28)
- **No more double "Working on it…".** The progress indicator now shows in one place while the agent runs (in the conversation), not twice. The bottom strip is reserved for the auto-build step afterwards.
- **The thinking wave is clearer.** Bigger, denser, livelier wave + the step text gently shimmers — reads as a live "thinking" state, not a flat dash.
  - FE `pages/reports/[id]/index.vue`: dock status strip gated on `autoBuilding` only (removed the `runActive` branch that duplicated the inline thread indicator). Wave path → 4-hump denser curve, `.cai-wave` 30×16→42×20, stroke 2.2→2.6, pulse 0.3–1→0.35–1.15, 1.3s; live-stage text gets `cc-shimmer`.
  - Note: a turn that ends in a clarifying question (e.g. ambiguous "this data" with multiple active sources) runs no `create_data`, so it shows "Working on it…" (no step to name) and produces no artifact — expected, not a bug.

## v1.58.0 — Data answers auto-build a dashboard  (2026-06-28)
- **Ask for data, get a dashboard — automatically.** When a chat turn pulls a dataset but doesn't make any visual, the agent now builds a dashboard for you in the background, so the Outputs panel fills in instead of staying empty. The dock shows "Building a dashboard from your data…" and the dashboard appears on its own.
  - BE flag `HYBRID_AUTO_ARTIFACT` (default OFF; ON for org 1a073f60). New `services/auto_artifact.py`: `schedule_auto_artifact(...)` fires a background `asyncio` task (strong-ref'd) after a successful chat turn that ran `create_data` (≥1 success Step) AND has zero artifacts; reuses `report_slides._generate_artifact(mode='page')` in a fresh detached session (reload by PK), fully fail-soft, idempotent (one build per report). Hooked in `completion_service.py` non-stream (~:920) + stream (~:2404) after the answer + sense_making commit. OFF = byte-identical.
  - FE `pages/reports/[id]/index.vue`: on run-end, if the turn produced data + no artifact, poll `/artifacts/report/{id}` every 6s up to ~3min (`autoBuilding`) so the auto-built dashboard appears without a refresh; the dock status strip reuses its wave to show the "Building a dashboard…" state.

## v1.57.0 — Progress always in view (docked status strip)  (2026-06-28)
- **You can always see what the agent is doing.** While it works, a thin live strip sits right above the ask box — the wave, the current step, and how long it's been running — with a Stop button. It stays put even when you scroll up through the conversation.
  - FE `pages/reports/[id]/index.vue`: added a persistent run-status strip in the composer dock (`runActive && lastSystemMessage`), reusing `runningStageText(m)` + `liveElapsed(m)` + `.cai-wave`. The composer was already pinned (`shrink-0`); the strip mounts just above it and is gated on the live run so it disappears when idle. Stop wired to `abortStream`.

## v1.56.1 — Working wave now actually shows in chat  (2026-06-28)
- **Fix:** the live "what's happening" wave now appears in the report chat while the agent works (it wasn't showing before).
  - The report conversation renders its own inline progress header in `pages/reports/[id]/index.vue`, NOT `components/AgentStepTimeline.vue` (which v1.56.0 edited). Moved the wave into the real renderer: the in-progress header ("Working · N steps · m:ss") and the bare "Thinking…" dots block both now show `wave · live step title · wave · elapsed`. Added `runningStageText(m)` (current running step title from `blocksToSteps`, friendly fallback) + `.cai-wave` CSS. `AgentStepTimeline.vue` keeps its copy for the surfaces that use it.

## v1.56.0 — "It's working" wave + a calmer home  (2026-06-28)
- **You can see the agent thinking now.** While it works, the chat shows a live wave with the actual step it's on — "Reading your data…", "Writing the query…", "Running the query…", "Composing the answer…" — plus an elapsed timer, instead of a flat "Thinking…". The text tracks the real run, not a canned loop.
- **The home screen feels alive and less empty.** A gentle wave sits under the greeting with a small "ready" line, filling the space above the ask box and matching the working-wave motif.
  - FE `components/AgentStepTimeline.vue`: running state replaced the spinner pill with a `wave · live stage · wave · m:ss` row. `currentStage` = the live running step's title (falls back to friendly verbs while no step has emitted); elapsed timer via a 1s interval started/stopped on `isRunning`. Done state keeps the "Thought process · N · Done" pill. SVG `scaleY` wave, `prefers-reduced-motion` respected.
  - FE `pages/index.vue`: idle 3-layer clay wave (`.home-wave`, slower/lower-amplitude than the running one) + `readyCaption` ("ready · grounded on N sources" / "ready when you are") between the subtitle and the composer; composer margin `mt-10` → `mt-6`.

## v1.55.2 — Sign-in hero now shows the real product story  (2026-06-28)
- **The animation on the sign-in screen now mirrors what the app actually does.** It walks the full flow end to end: connect a real data source (Postgres, Snowflake, BigQuery, SharePoint, MySQL, Redshift, Databricks, ClickHouse, MS Fabric, Power BI…), ask a question in plain English, watch it pick the right model automatically, get an answer with a clear "what to do next" decision, then build a dashboard, a slide deck, and a scheduled email — all on a tight loop.
  - FE `pages/users/sign-in.vue`: rewrote the right-panel showcase. Real connector-type names (from the 46-type catalog) replace the old Stripe/GA4 mock; added scenes for Auto model routing (`Auto → tier · model`), a Decision callout in the answer card, a dashboard build (KPI tiles + chart), a slide-deck render, and a schedule→email confirmation. Scene state machine `scene 1..6`; per-turn data drives sources/model/decision/kpis/slides.

## v1.55.1 — Connector authz hardening (un-skippable guard)  (2026-06-28)
- **Hardening only — no visible change.** The owner/super-admin permission check on connector edit/delete/test is now wired into each route's signature, so a future change can't accidentally ship a connector route without the access check.
  - BE `routes/connection.py`: new FastAPI dependency `guard_owned_connection` wraps `_guard_private_owner` and is added as `Depends(...)` to all 9 mutate/test/reindex/tools routes (replaces the in-body `await _guard_private_owner(...)` calls). Routes that need the loaded row take `connection=Depends(guard_owned_connection)`; the rest take `_guarded=Depends(...)`. Same owner-or-admin semantics; the guard is no longer an easily-dropped body call.
  - Verified live (org 1a073f60): member PUT own 200 / member PUT+DELETE org 403 / super-admin PUT member's private 200.

## v1.55.0 — Edit fixes: roomy form, owner + super-admin edit, Connectors for everyone  (2026-06-28)
- **Edit Connection is readable again.** The edit form opened in a cramped narrow box; it now uses the same wide two-pane layout as Add (form + "How to get each value" side by side).
- **Edit your own connectors — and super admins can edit any.** You can now edit, test and delete connectors you created right from the Connectors page (not just inside a studio). Super admins can edit/delete any connection in the org, including others' private ones.
- **Connectors page is open to everyone.** Every member sees the Connectors page in the nav: the connectors they created, ones shared to them, and org-wide ones. Creating org-wide/shared stays controlled.
  - FE: `ConnectionDetailModal` edit `UModal` width `sm:max-w-xl` → `sm:max-w-xl lg:max-w-5xl`. `useAppNav.ts` Connectors item: dropped the `create_data_source` permission gate (visible to all members; Manage group is per-item gated so it appears with just Connectors).
  - BE `routes/connection.py`: `_guard_private_owner` rewritten as OWNER-OR-ADMIN (super-admin/manage_connections bypass → manage ANY connection incl others' private; else caller must own it; org connectors → non-admin denied). Dropped the admin-only `@requires_permission('manage_connections')` decorator on GET `/{id}` (detail), PUT `/{id}`, DELETE `/{id}`, POST `/{id}/test`. GET detail now returns full config + has_credentials to the OWNER or an admin (was admin-only), so owners can edit their own.
  - Verified: member edits/sees own (200), blocked on org connector (403); super admin GETs+PUTs another user's private connector (200, full config). Credentials still never returned in the UI.

## v1.54.0 — Connectors table + one-click sharing panel  (2026-06-28)
- **All your connectors in one table — set sharing from there.** The agent's Connectors page (and the org Manage → Connectors page) now show every connection in a clean table with a **Who can use** badge per row. New connectors are **Private by default**; click the badge to open a sharing panel and switch to Shared (pick people/groups) or Org-wide.
- **Cleaner add flow.** Creating a connector for an agent now lists only the types you can set up with your own credentials (no admin sign-in needed); you pick who can use it afterward from the table — not buried in the create form.
  - FE: new `components/ConnectorsTable.vue` (rows: name/type/owner/visibility badge/active/sync/actions; `context='studio'|'org'`) + `components/ConnectorSharingPanel.vue` (right-hand drawer: Private/Shared/Org radios + grant picker, `PATCH /connections/{id}/visibility`). `StudioConnectors.vue` card grid → table + All/Mine/Shared chips; `pages/connectors.vue` card sections → same table + All/Mine/Shared/Org chips. `AddConnectionModal` gained `individualOnly` (hides the 6 admin-OAuth types sharepoint/onedrive/google_drive/ms_fabric/powerbi/mcp) + `deferSharing` (hides the visibility selector, creates Private). Studio passes both; org passes `deferSharing` only.
  - Credentials never shared at any level (query path stays `system_only`); read-only rows (admin/org connectors) show a non-clickable badge + Activate only.

## v1.53.0 — Connector visibility: Private / Shared / Org-wide  (2026-06-28)
- **Choose who can use each connector you build — three levels.** When you create or own a connector you can set it **Private** (only you), **Shared** (specific people or groups you pick), or **Org-wide** (everyone in your organization). Any member can do this themselves — no admin needed.
- **Publish or lock down any time.** Flip a connector between Private, Shared and Org-wide from its card. Shared lets you manage exactly which users/groups have it. Whatever the level, your credentials are never shown to anyone — others can query the data through an agent but can't see or edit the connection.
  - BE: `connections.visibility` enum `private|shared|org` (migration `connvis1`, backfills legacy owner-NULL rows → `org`); `owner_user_id` now always = creator (keeps edit rights at every level). `ConnectionCreate.visibility` + `ConnectionSchema.visibility`. POST `/connections`: any org member may create at ANY level (non-private gated by `HYBRID_AGENT_CONNECTORS`); admin-only-for-shared gate dropped. New `PATCH /connections/{id}/visibility {visibility, grants?}` (owner-or-admin) — writes/clears connection `resource_grants` for the shared level, audit-logs `connection.visibility_changed`. Resolution updated in `private_connector_guard.is_private` (now `visibility=='private'`), `connection.py list_connections._conn_visible` (org→all, shared→owner+granted/DS, private→owner) and `studio_sources.py` (`mine` = I own at any level; `shared` = org + shared-to-me; `+visibility` on each item). Query/runtime path UNCHANGED (creds still `system_only`).
  - FE: `AddConnectionModal` 3-way visibility selector (replaces admin-only scope toggle) → `ConnectForm` sends `visibility`; `StudioConnectors` + `pages/connectors.vue` show a Private/Shared/Org badge and owner controls (Make Private / Share… / Publish org-wide) calling `PATCH …/visibility`; Shared opens the existing `ManageConnectionAccessModal` user/group picker.
  - Verified live (member rahul, self-service): created `org` + `private` connectors (owner=self); PATCH private→org→shared all 200 + DB reflects; studio `mine` lists all 3 levels with `visibility`, `shared` lists org connectors. Migration `agentconn1→connvis1` applied on org `1a073f60`; backfill correct.

## v1.52.0 — Every connector type in the per-agent "Add connector"  (2026-06-28)
- **Build any kind of private connector for an agent — all ~44 types.** The agent's **Add connector** now opens the full connector catalog (PostgreSQL, MySQL, Snowflake, BigQuery, Databricks, MS Fabric, SharePoint/OneDrive/Google Drive, REST, CSV and more) — the same catalog as the admin Connectors page — instead of just 6 hard-coded types. It's still private to you and bound to this agent, and it activates automatically.
- **Your existing admin connectors (SharePoint etc) already work here.** Any connector an admin sets up org-wide appears in the agent's **Shared Connectors** tab — press **Activate for agent** to use it. Each user signs in with their own identity for file connectors.
  - FE: the studio **Add connector** flow now mounts the shared `AddConnectionModal` (catalog → `ConnectForm` → indexing) forced to PERSONAL scope, replacing the hand-built 6-type form (that form is kept for in-place EDIT only). On `@created` the new connection is activated for the agent. `AddConnectionModal` + `ConnectForm` gained a `studioId` prop; `ConnectForm` sends `studio_id` on the personal-create POST.
  - BE `schemas/connection_schema.py`: `ConnectionCreate.studio_id` (optional). `routes/connection.py` POST `/connections`: when `scope=personal` + `studio_id`, validates the studio is in the caller's org and sets `connection.studio_id` so it lands in that agent's **My Connectors** tab. Shared scope ignores it.
  - Verified live (member rahul, studio Rahul2): created a `sqlite` personal connector with `studio_id` bound → appears in `mine` → **Activate** → `active:true` + DataSource pinned → delete clean. SharePoint/file connectors reach agents via the org-shared + Activate path (admin creates once; no per-agent code).

## v1.51.1 — Connectors tab now visible to non-admins  (2026-06-28)
- **Normal users can see the Connectors tab again.** The per-agent Connectors page (and Teach / Reports tabs) were only showing for admins. They now appear for every member in an org where the feature is on.
  - Root cause: studio rail/tab gating reads `GET /api/organization/hybrid-flags` for the per-org `effective` flag, but that endpoint was `@requires_permission('manage_settings')` → 403 for members → FE caught it → all flag-gated tabs stayed hidden.
  - Fix `routes/organization_settings.py`: dropped the blanket admin decorator on the GET; admins still get full rows (label/note/override/default — the Settings flag editor), non-admins get a minimal `{env_name,key,effective}` projection (booleans only, no config internals). PUT stays admin-only. Flag effectiveness is per-ORG not per-role, so members must be able to read it.
  - Verified: rahul (member) now gets 71 rows incl `HYBRID_AGENT_CONNECTORS effective:true`, no notes/override leaked; admin still gets full rows.

## v1.51.0 — Connectors inside each agent (Activate for agent)  (2026-06-28)
- **Each agent now has its own Connectors page.** Open an agent → **Connectors** in the left rail to see two tabs: **My Connectors** (private connectors you build for this agent) and **Shared Connectors** (admin-configured ones you can reuse).
- **Activate a connector to let the agent use it.** Press **Activate for agent** on any connector — only *active* connectors are queryable by the agent, and activating runs a data sync automatically. Deactivate any time to detach it.
- **Build, test and manage private connectors right where the agent lives** — add, edit, test and delete without leaving the agent.
  - FE `components/studio/StudioConnectors.vue`: two-tab (My/Shared) grid; per-card **Activate / ✓ Active · Deactivate**; sync date; private-only Test/Edit/Delete; "Add connector" modal creates+activates a private connector. Self-gates on `HYBRID_AGENT_CONNECTORS`. Mounted at `pages/studios/[id]/index.vue` tab `connectors` (line ~2253/1071) — no index.vue change needed.
  - BE `routes/studio_sources.py`: `GET /studios/{id}/connectors` now returns `{mine, shared}` (each item `{connection_id,name,type,owner_user_id,is_org,active,data_source_id,sync_status,last_synced_at}`; shared visibility reuses connection.py `_conn_visible` — admin sees all org connectors, member sees granted/public-DS-backed; private-not-owned never listed). New `POST/DELETE /studios/{id}/connectors/{connection_id}/activate` — ensures a DataSource wraps the connector, pins/unpins `StudioDataSource`, triggers `schedule_bootstrap_on_source_pin` sync. `active` = a wrapping DataSource is pinned (not soft-deleted).
  - Reuses existing `StudioDataSource` pin model — **no new table / migration**. EPHEMERAL (cp + restart + fe-sync), not baked.

## v1.50.0 — Two-tier connectors + member privacy  (2026-06-28)
- **Everyone can build their own connections now.** Connectors split into two groups: **Shared** (set up by your admins, reusable) and **My Connections** (private connectors you create yourself — only you can see or use them). Each user can connect their own database without admin help.
- **Admins choose who sees a shared connector.** A new "Manage access" on every shared connector lets an admin grant a specific person or group permission to use it — no more all-or-nothing.
- **Share the agent, not the connection.** When an agent is pinned to a connector and you share that agent, teammates can ask questions and get data through the agent — without ever seeing or touching the underlying connection or its credentials.
- **Members no longer see each other's email.** On the Access & Members page a regular member now sees other members' name, role and groups — but their email and login details are hidden. Admins still see everything; you always see your own.
  - Connectors: `connections.owner_user_id` (NULL=shared / set=personal private) drives the split. `POST /connections` takes `scope: shared|personal` — shared = admin-only (owner NULL), personal = any member (owner FORCED server-side to the session user, no spoofing), gated on `HYBRID_AGENT_CONNECTORS` (already ON). `list_connections` returns `{granted-shared ∪ own-private}`; a member's own private connector is always visible to them even with no grant. `owner_user_id` added to `ConnectionSchema`.
  - Access grants reuse the existing polymorphic `resource_grants` table + `rbac.py` `/organizations/{org}/resource-grants` (GET/POST/DELETE, `resource_type=connection`). FE `ManageConnectionAccessModal.vue` (user/group picker). Private connectors are non-grantable by design (`_deny_share_private_connector`).
  - Agent-as-proxy: runtime credential resolution (`data_source_service.resolve_credentials_for_connection`) uses the studio's bound connection creds under `auth_policy=system_only` for any caller — `require_owner`/`filter_visible` guard only the management plane, never the query path. Who-may-run gated by `AGENT_ACL` (ON); whose-creds by `auth_policy`.
  - Members PII: `routes/organization.py get_members` redacts non-admin viewers — masks other members' email (`a***@domain`), nulls note/auth-sources/login/external. Own row + admin (full_admin/manage_members) unaffected.
  - DDL (manual, agentconn1 never baked into the live image): `connections.owner_user_id` + `studio_id` columns added. Also hot-cp'd `models/connection.py` + `services/private_connector_guard.py` which were MISSING from the running container (lost on a prior force-recreate). EPHEMERAL — not baked.

## v1.46.0 — Safe-enable wave + lightweight Forecasting + per-agent Self-learning  (2026-06-27)
- **Turned on the stable feature set.** Governance, Column Intel, Compliance Scan, File Browser, Per-agent Connectors, One-click Dashboard/Slides/Excel, Rich report emails, Scheduled reports, Auto-configure, Bi-temporal facts, Join-graph context, Quotas, Workflows, plus safe learning helpers — all enabled and smoke-tested.
- **Forecasting with no heavy install.** The forecast tool now uses Holt-Winters/ETS statistics (with a linear fallback) plus a plain-English summary of the trend — accurate numbers and a readable takeaway, without the old 200MB dependency.
- **Each agent can self-improve on its own schedule.** A new "Self-learning" card on a studio lets the owner switch on auto-improvement and pick how often — every 6 hours, daily, weekly or monthly (at an hour you choose). It only proposes examples & rules for your review; nothing auto-applies. An admin master switch governs it org-wide.
- **Removed a dead toggle.** The non-working "Context Compaction — LLM" switch is hidden until it's actually built.

## v1.49.0 — Slides that actually build, an Outputs feed, and a Session Summary  (2026-06-28)
- **Slide decks now build reliably.** Presentations were silently failing (the generated chart code used a blocked function) while the chat still said "created successfully". Fixed the generator and made failures honest — if a deck can't build you now see a clear failed state with a Retry, not a fake success.
- **Outputs is now a full feed.** Instead of just the latest answer, the Outputs panel shows every turn — the question you asked, a timestamp, the answer, the decision, and the artifacts produced (dashboard / slides / Excel) with their status. Newest on top; click to expand older turns.
- **New Session Summary.** A pinned card at the top of Outputs synthesises the whole report across all your turns: a headline, the key decision, the main findings, what was produced, and suggested next steps. It updates as you add turns (shows "stale" with a Refresh).
- **Clicking a slide opens the slide.** Opening a presentation from the chat now lands on the Slides view (and shows the latest good deck), instead of opening the dashboard or a blank panel.
  - Slides: `create_artifact.py` slides prompt gained a hard SANDBOX-RULES header (ban getattr/hasattr/eval/exec/open; use `'x' in dir(obj)`) + the example helpers were rewritten getattr-free (they were the source the LLM copied). Failure path: observation now reports failure + gates the success wording on `status!='failed'`. A retry rebuilt a clean `completed` deck.
  - Outputs feed: `OutputsFeed.vue` (per-turn Q + ANSWER + DecisionCard + artifact chips), rendered from `ChatSummary.vue` (`:messages`). Q/A paired by user↔system rows; artifacts mapped by recency.
  - Session Summary: `app/ai/knowledge/session_summary.py` (one cheap `is_small` haiku pass, never raises) + GET/POST `/reports/{id}/session-summary` + new `reports.session_summary` JSON col (manual `ALTER`) + `SessionSummaryCard.vue` (stale badge + Refresh, auto-build once). Flag `session_summary` (org setting, default ON).
  - Slides panel: `hasGoodSlidesArtifact` requires `completed`; new `pendingSlides` "Building…" + `failedSlides` Retry; refetch artifacts on run-end; `generateSlideDeck` polls up to 4 min (build ~120s > tool timeout). Artifact routing: `handleOpenArtifact` routes by `mode` and, for a non-completed clicked id, selects the latest completed same-mode artifact. EPHEMERAL, not baked, not pushed.

## v1.48.0 — Explainable dashboards + no-surprise decisions  (2026-06-28)
- **Dashboards now explain themselves.** Every generated dashboard leads with a Decision (Watch / Act / Hold + confidence) and a Key Insights card, and every KPI and chart has an "Explain" you can open — Reading, Why, So-what, and what to Do. Goes past the usual descriptive charts to tell you the driver, the impact and the next move. Anomalous widgets get a "Watch" badge.
- **The decision no longer pops up by surprise.** After your answer, the assistant shows "Reading the result… forming a decision" right where the Decision card will land, and briefly holds the composer so you can read it before asking the next question. If there's no decision to make, nothing changes.
- **The Outputs panel shows a loading animation.** While a result is generating, Outputs shows the same shimmer the dashboard uses instead of looking empty.
- **The model picker now defaults to Auto.** New reports start on Auto (smart routing); you can still pick any specific model, and saved choices are kept.
  - Flag `dashboard_key_insights` (org setting in `organization_settings_schema.py`, default ON; fail-soft ON if absent). NO migration. EPHEMERAL (backend `docker cp` + ONE `docker restart ca-app` + `fe-sync`), NOT baked, NOT pushed. Built via 3 parallel sub-agents (2 backend + all-frontend, non-overlapping files).
  - Explainable dashboard: `create_artifact.py` `_build_page_prompt` injects a flag-gated `explainability_block` (grounded Decision callout + Key Insights above the KPI row + per-widget collapsible `<details>` Explain with Reading/Why/So-what/Do + Watch badge). Render path = native `<details>` JSX (the `InfoPopover`/`viz` prop only exposes Data/Code tabs). ROOT CAUSE the old `decision_banner_block` was empty: dashboards = `create_artifact` page React built MID-run; sense_making is POST-run. Grounding rules forbid invented numbers. (A first same-day edit to the secondary `create_dashboard.py` semantic builder was the wrong target — dormant.)
  - No-surprise decision: `completion_service.py` stream path emits new SSE `sense_making.pending` before `build_sense_making` (existing `completion.finished` = unlock). FE `index.vue` `decisionPending` ref (FAIL-OPEN) → pending shimmer card in chat+Outputs + `PromptBoxV2.canSubmit` adds `&& !props.decisionPending` + inline locked note.
  - Outputs loader: `ChatSummary.vue` renders `<DashboardSkeleton mode="page" />` while `generating` (`:generating="runActive"` from `index.vue`, both mounts).
  - Picker default Auto: `PromptBoxV2.loadModels` defaults `selectedModel='auto'` when nothing persisted (loads auto-flag first); saved/explicit pick preserved; other options untouched.

## v1.47.0 — Auto model selection  (2026-06-28)
- **Let the assistant pick the model for you.** The model picker now has an **Auto** option. Pick it once and each question is routed to the right model automatically — a fast, low-cost model for simple lookups and counts, a stronger model for forecasting, "why" questions, comparisons and multi-step analysis. Cheaper on average and you stop babysitting the dropdown.
- **You always see which model it chose.** While the answer is generating you get an "Auto → <Model>" badge above it, the picker chip reads "Auto · <Model>", and the Outputs panel shows "routed to <Model>". Hover the badge to see why it picked that tier.
- **Never gets in the way.** If anything is unsure, it falls back to your normal default model — behaviour is identical to the feature being off.
  - Flag `HYBRID_AUTO_MODEL` (default OFF; ON for org `1a073f60` via DB override). New `app/ai/knowledge/auto_model.py`: deterministic 0..1 complexity score (length + keyword regex: forecast/why/correlate/compare/segment push up, count/list/show push down, multistep/artifact bump) → tier Fast(<0.40)/Balanced/Reason(>0.60) → cheapest capable of the org's enabled models (Fast=cheapest small, Reason=flagship regex else priciest, Balanced=median non-small). ONE cheap LLM tie-break (small model, `usage_scope="auto_model"`) ONLY in the fuzzy band [0.40,0.60]; everything else is $0/0ms. `choose_auto_model` NEVER raises → org default on any error.
  - `completion_service.py`: helper `_auto_pick_model`; sentinel `model_id="auto"` handled at the 3 model-resolution sites (estimate path skips the classifier → default, to avoid per-keystroke cost). Decision persisted to the answer completion's `completion.auto_model` JSON + emitted LIVE as an `auto_model` SSE event at stream start. v2 schema gains a top-level `auto_model` field (assembly both sites). Flag property + `UPGRADE_FLAGS` (Intelligence/experimental) + snapshot.
  - FE: `PromptBoxV2.vue` Auto option (gated on `/api/organization/hybrid-flags` → `HYBRID_AUTO_MODEL.effective`) + "Auto · <Model>" label via `:auto-picked` prop. `pages/reports/[id]/index.vue`: `auto_model` SSE case → live `⚡ Auto → <Model>` chip, `latestAutoModel` computed, `auto_model` mapped in both completion maps + piggy-backed onto the sense-making live-patch. Outputs `ChatSummary.vue` "routed to" pill via `:auto-model` prop. EPHEMERAL (docker cp + fe-sync), NOT baked, NOT pushed.
  - Flags enabled on org `1a073f60` via DB overrides (62 effective). Multi-worker note: `ca-app` runs `--workers 4`; the PUT `set_override` only patches one worker, so each enable wave ends with ONE `docker restart ca-app` to converge all workers from DB. `HYBRID_CONTEXT_COMPACT_LLM` added to `HIDDEN_FLAGS` (TODO(compress-llm) stub).
  - `forecast.py` rebuilt: Prophet → statsmodels `ExponentialSmoothing` (seasonal when ≥2 cycles → trend-only ≥3 pts → numpy-linear ≥2 pts), ±1.96σ band widening with horizon, optional LLM narrative via `runtime_ctx['model']` in `asyncio.to_thread` (fail-soft). `schemas/forecast.py` +`method`,+`narrative`. `requirements_versioned.txt`: `prophet==1.1.6` → `statsmodels==0.14.2`+`patsy==1.0.2` (10MB, not 200MB). Flag meta `needs_dep`→`stable`.
  - Per-agent self-learn: config on `studio.config['self_learn']` (no migration). New `routes/studio_self_learn.py` (`GET/PUT /api/studios/{id}/self-learn`, owner/editor-gated), `schemas/self_learn_schema.py`, `components/studio/StudioSelfLearn.vue` (Autopilot tab). `studio_learn_daemon.py` rewritten: override-aware `daemon_enabled()` (reads `flags.STUDIO_LEARN_DAEMON` — fixes UI toggle being ignored), per-studio `is_due()`/`next_run_estimate()` cadence loop, hourly tick, stamps `last_run_at`. `flags.STUDIO_LEARN_DAEMON` property + snapshot.
  - LANDMINE: cp'ing host `main.py` (ahead of image) surfaced that `studio_reports.py`, `report_slides.py`, `connection_files.py` were hot-cp-only and missing from the image — re-cp'd all 3, now baked.

## v1.45.0 — UI first-run setup + connector org auto-join + OpenRouter from UI  (2026-06-27)
- **First-run setup screen.** A brand-new install now shows a "Create your super-admin" screen on the sign-in page. The first account you make becomes the owner, and sign-up closes automatically right after — it never appears again. No more editing env files to bootstrap the admin.
- **Sign in with your company directory and just land in.** Logging in with LDAP, Google, Microsoft, Keycloak or SSO now drops you straight into the workspace instead of asking you to "Create an organization" — you're auto-added to the org. Already-stranded accounts are rescued on their next login.
- **Set up OpenRouter from the UI.** Paste your OpenRouter key in Settings → LLM and the ready-made models (Claude Sonnet/Haiku/Opus, GPT, Gemini) light up immediately with a default selected. No key in env, ever. Add more models anytime.
  - `auth.py`: `on_after_register` now elevates the very first user (`users==1 & orgs==0`) to `is_active/is_verified/is_superuser` so the UI signup yields a real super-admin (mirrors `seed_admin.py`). New `_ensure_user_in_org(email)` auto-joins externally-authenticated users to the primary (oldest) org as `role=member` + matching system RoleAssignment; wired at 6 points (LDAP new+existing, OAuth new + returning-by-account + linked-by-email). Idempotent, fail-soft, no-op before any org exists.
  - `dash_settings.py`: `GET /api/settings` returns `needs_setup` = (`user_count==0`), FAIL-CLOSED (count error → False → login, never signup). `sign-in.vue` renders the create-admin form when `needs_setup`, POSTs `/api/auth/register` then auto-logs-in; reuses the existing clay design (badge + name field + lock note + Settings→Models pointer).
  - `llm_service.py`: `create_provider` now UPSERTS — `_find_upsert_target` folds a POST onto the shipped OpenRouter/custom provider (matches across the openrouter↔custom family by base_url, defaulting OpenRouter's endpoint), so "Save Provider" sets the key on the canonical provider instead of 409-ing or duplicating. `_apply_key_and_models_to_existing` sets the key, adds only genuinely-new models (by `model_id`), and `_enable_preset_models` lights up preset models on the blank→set transition. Preset-provider update unblocked for key/base_url/model changes (delete still blocked). Keys stay Fernet-encrypted, never returned. `docker-compose.build.yaml`: added `DASH_ADMIN_*` passthrough so the env-seed path also works headless.

## v1.44.1 — Auto-persistent encryption key  (2026-06-27)
- **Zero-config install.** You no longer have to generate an encryption key before first boot — the app makes one automatically and remembers it, so saved API keys keep working across restarts.
  - `start.sh`: `DASH_ENCRYPTION_KEY` precedence = explicit env/.env > key persisted at `/app/backend/uploads/.dash_encryption.key` (on the durable `ca_uploads` volume) > generate-once-and-persist (umask 177, atomic write, perms 600). Removes the old "temporary key → users logged out on restart" footgun (`config.py:76` only set it in-process). Explicit env still wins and is mirrored to the volume. Override path via `DASH_ENCRYPTION_KEY_FILE`. No compose/volume change (reuses existing `ca_uploads`).

## v1.44.0 — Personal groups (My Groups)  (2026-06-27)
- **Make your own contact groups.** Any member can now create personal groups of people — open **My Groups** in the sidebar, name a group, add members, done. No admin needed.
- **Share agents to your groups.** When you give people access to an agent, your personal groups show up in the picker (tagged "mine") right alongside org and AD/LDAP groups — pick one and everyone in it gets access.
- **Names are unique across the organization.** If a group name is already taken (by anyone, personal or org), you'll be told instead of making a confusing duplicate.
  - **Backend (already built, now deployed):** `routes/me_groups.py` (`/api/me/groups` CRUD + `/api/me/contacts`) + `services/me_groups_service.py`, all gated by `flags.USER_GROUPS` (404 when off). Personal group = `Group` row with `owner_user_id` set; every query scoped to `owner_user_id == current_user.id` so it can never touch org/admin/LDAP groups. Creator auto-added as a member. Unique name = existing `UNIQUE(organization_id, name)` spanning personal + org groups → 409 on collision.
  - **DB:** added missing `groups.owner_user_id varchar(36) REFERENCES users(id)` column + index (model had it, prod DB didn't). Flag `HYBRID_USER_GROUPS` enabled via `organization_settings.config.hybrid_overrides` for org `1a073f60`.
  - **FE:** new `pages/settings/my-groups.vue` (full CRUD, default layout — visible to ALL users, not behind the permission-gated Settings rail) + nav entry in `composables/useAppNav.ts` (no permission). `StudioAccessPicker.vue` `loadGroups` now merges `/me/groups` (personal, "mine" badge) with the admin `/organizations/{org}/groups` (skipped on 403 for non-admins). `StudioCreateGroup.vue` now creates a PERSONAL group via `/me/groups` + members from `/me/contacts` (both work for non-admins; removes the old 402/403 on the admin org-groups route).
  - LANDMINE: the running image's `main.py` predates these route files — deploying meant restoring the image `main.py` and surgically adding only the `me_groups` import + `include_router`, NOT cp-ing the host `main.py` (host is ahead and imports `studio_reports` etc. not in the image → ImportError boot loop).

## v1.43.0 — User provenance + creation locked to super admin  (2026-06-27)
- **See where each person came from.** The Members table now shows a **Source** badge per user — Local, LDAP, SSO (with the provider), or SCIM — and a merged person shows all of them at once.
- **Only a super admin can create users now.** The Add Member and Import buttons are hidden for everyone else; LDAP and SSO still provision their users automatically.
- **Groups show their origin too** — each group is tagged Local or AD/LDAP/Okta/SCIM, and directory-synced groups lock their membership editing (managed by the sync).
- **One identity per email.** If someone signs in with SSO or LDAP using the same email as an existing account, it links to that one account instead of making a duplicate — and there's now a switch to require a verified email before that linking happens.
  - **User provenance:** new `auth_sources: string[]` on each member row (`GET /organizations/{org}/members`), derived in `routes/organization.py` `_derive_auth_sources()` from `User.ldap_dn` / `oauth_accounts[].oauth_name` / `scim_external_id` (else `["local"]`); eager-loads `oauth_accounts`. `MembershipSchema.auth_sources` added. FE `MembersComponent.vue` Source column (badges Local/LDAP/SSO·provider/SCIM), reads `is_superuser` from session (top-level, per nuxt.config sessionDataType).
  - **Creation lock:** `add_member` + `create_user_directly` routes add an explicit `current_user.is_superuser` 403 on top of `manage_members`. FE hides Add Member + Import unless `is_superuser`. LDAP/SSO auto-provision (in `core/auth.py`) untouched.
  - **Group provenance:** `GroupsManager.vue` Source badge from `Group.external_provider` (AD/LDAP/Okta/SCIM vs Local); synced groups disable member add/remove (`title="Managed by <provider> sync"`).
  - **Merge model + hardening:** identity is keyed by email — SSO `oauth_callback` links onto an existing user by email, LDAP `_ldap_authenticate` finds-or-provisions by email (one `users` row, multi-credential). New env `OAUTH_TRUST_EMAIL` (default **true** = unchanged behavior); set false to refuse SSO email-linking unless the provider asserts a verified email. OpenWebUI parity note: they gate this behind opt-in `OAUTH_MERGE_ACCOUNTS_BY_EMAIL` — we now have the equivalent switch.
  - Built by 4 parallel subagents (disjoint files: organization.py+schemas / MembersComponent.vue / GroupsManager.vue / auth.py), fixed `auth_sources` contract. No migration, no flag.

## v1.42.1 — Create groups in-app + groups work without a license  (2026-06-27)
- **+ Create group** now opens a real form right from Add access — name it, add org members, done — instead of sending you to another screen.
- Fixed: org **Groups** (and the Add-access list) were silently empty on installs without an enterprise license. Groups, group membership and the group picker now work on every tier.
  - Un-gated `custom_roles` in **both** `app/ee/license.py` `COMMUNITY_FEATURES` (backend 402 fix) **and** `frontend/ee/composables/useEnterprise.ts` `COMMUNITY_FEATURES` (FE tab-visibility fix — the **Roles** + **Groups** tabs under Settings → Access & Members were hidden by `hasFeature('custom_roles')` even after the backend un-gate). New `StudioCreateGroup.vue` (name + description + org-member multi-select via `GET /organizations/{org}/members`, `POST /organizations/{org}/groups` then `…/members`); wired into `StudioAccessPicker`'s `+ Create group`. Created groups are **org-level** (shared pool, `owner_user_id` NULL), not per-user.

## v1.42.0 — Group-based agent access + merged Access tab  (2026-06-27)
- Sharing an agent now puts it straight into the right people's accounts: share it to a **group** (including teams synced from Active Directory / LDAP) and every member instantly sees it in their Studios list and the chat agent dropdown — no manual add per person.
- New **Add access** panel on an agent: pick groups, set each to **Viewer** or **Editor**, see live member counts, and tell apart AD-synced groups (badge) from local ones.
- One cleaner **Access & Members** screen — the old separate "Members & Share" tab was folded in, so access, people, model and delete all live in one place.
- Access choice simplified to **Private** (only the people & groups you grant) vs **Public** (everyone in your org); share-by-link moved under an Advanced option.
- "Sync from AD/LDAP" button to pull the latest groups, and a shortcut to create a new group while granting access.
  - New flag **HYBRID_GROUP_ACCESS** (default OFF). Reuses the generic `ResourceGrant` table (`resource_type='studio'`, `principal_type='group'`, `permissions` JSON) — **no migration, no new table**.
  - Backend: `services/studio_access.py` gains `user_group_ids()` + `group_granted_studio_roles()`; `resolve_studio_access` adds a group step (write→editor, read→viewer, strongest grant wins) before org-scope. `GET /studios` list query OR-includes group-granted ids, so a shared agent auto-appears in the studios list AND chat dropdown (both source `/studios` via `useAgent.ts`). Routes `GET/POST/DELETE /studios/{id}/group-grants` (owner-only mutate, viewer+ list, flag-gated → []/404 when off).
  - Frontend: merged tab (`studios/[id]/index.vue` — removed `members` tab + section, `?tab=members`→`access` redirect, Delete folded into `StudioAccess.vue`). `StudioAccess.vue` Private/Public toggle + Link-as-advanced; Groups list (role dropdown + revoke) above People; self-gates on `HYBRID_GROUP_ACCESS` via `/organization/hybrid-flags`. New `StudioAccessPicker.vue` (searchable groups, member counts, AD/local badges, Viewer/Editor, `Sync from AD/LDAP` → `POST /enterprise/ldap/sync`, `+ Create group`). Reuses existing LDAP/OIDC group-sync (`ee/ldap/sync_service.py`) + RBAC group CRUD.
  - Deferred: P5 inline create-group modal (button currently points to Manage → Groups).

## v1.41.0 — Live training log + AI column meanings  (2026-06-27)
- **Watch your agent train.** The studio Auto-pilot now has a live **Training log** under the Train card: a Claude-Code-style terminal that streams each step as it runs — which model it's using, what it profiled, how many queries/goldens it wrote, and the exact error text if a step fails (no more silent frozen spinner). Switch between a clean **Steps** summary and the full **Logs** terminal, with a **Reset** button to clear a stuck run.
- **Column meanings fill themselves.** Every column in your data now gets a plain-English meaning written for it — automatically during Auto-train, or on demand with the new **Suggest column meanings** button on the Semantic tab. Before, columns sat at "No meaning yet" forever because nothing ever wrote them; now the agent actually understands each field.
- **Coming-soon tiles are clearer.** Infographic and Insight Map are now marked "Soon" and dimmed (like Forecast and Anomaly) instead of looking clickable. Excel stays live.
  - Train log: `train_orchestrator.py` keeps a capped, timestamped `log[]` in `_train_status` via a per-run logging handler that captures the trainer + LLM-client log lines (model/tokens/counts) + explicit `▸ stage` markers; persisted (tail-capped) to `Studio.config['_train_status']`, served by `GET /studios/{id}/train/status`. New `POST /studios/{id}/train/reset` (`reset_status`) clears a stuck run. FE `studios/[id]/index.vue`: inline panel under the TRAIN card, Logs⇄Steps toggle, warm-dark terminal (auto-scroll, level colors), Reset/Retry.
  - Column meanings: new `propose_column_meanings()` + `build_column_meaning_prompt()` in `knowledge_proposer.py` (LLM → blank `SemanticColumn.meaning`, writes `status='pending'`, never overwrites approved); `POST /api/knowledge/ai-suggest-columns/{ds}` (gated `SEMANTIC_LAYER`); folded into the Auto-train `semantic_metrics` stage (auto-approved like its siblings; detail now reports `N col meanings`). FE `SemanticTab.vue` button. Built by 3 parallel subagents.
  - Cards: `reports/[id]/index.vue` Infographic + Insight Map → dimmed `SOON` non-clickable tiles.

## v1.40.0 — Cleaner chat, one warm canvas  (2026-06-27)
- The center chat now reads like a modern AI workspace: collapsible thinking, tool steps threaded with connector lines and status dots, one-line tool rows, and a clean serif answer. Same engine and behavior underneath — purely a visual refresh.
- The whole report is now one continuous warm canvas. Before, the moment the agent produced a dashboard or answer, the right "Outputs" panel turned cool white and clashed with the warm chat — that colour jump is gone; chat and Outputs are the same warm tone.
- A few rough edges fixed: garbled vertical table names in tool rows (now a tidy "N tables" chip you can hover), a spinner that could hang while the agent waited for your answer (now a clear "Waiting for your answer — run paused" chip), and larger, more readable answer text and tables.
  - Cosmetic-only edits in `pages/reports/[id]/index.vue` (P0–P5): center surfaces `bg-[#F6F1EA]`→`#FAF8F3`; `.cc-step` threaded tool rows (connector rail `#E9E0D3` + status dots, `--done` green / `--err` amber); live `cc-shimmer` header + `liveElapsed(m)` timer; `awaitingClarify` paused chip replacing the perpetual polling spinner; markdown bumped 13→15px / line-height 1.7 / serif headings + hairline tables; empty-state eyebrow. `components/tools/CreateDataTool.vue`: table-name list → count chip (`N tables`, full list on hover) + `flex-wrap`/`min-w-0` no-garble.
  - `components/report/SplitScreenLayout.vue`: the Outputs/right pane and its inner card warmed `bg-white`/`bg-[#f8f8f7]` → `bg-[#FAF8F3]`, border `#E9E0D3` — fixes the warm→white jump when a report opens its dashboard/answer dock.
  - Backend `services/report_service.py`: `create_report` now drops a stale/unknown `studio_id` (verifies it exists in the org, else nulls it) — fixes a fresh-DB `ForeignKeyViolationError` where an old browser-cached studio id blocked report creation.

## v1.39.0 — One-click Dashboard + Excel too (no more empty panels)  (2026-06-27)
- The empty **Dashboard** view now has a **Generate dashboard** button: turn the report's charts into an interactive dashboard (KPI cards + chart grid) in one click — same as the slide deck, no chatting.
- The **Excel** tab now fills itself: every chart in the report becomes a sheet of real rows and columns, instead of "No spreadsheet yet".
- One toggle now controls all three one-click builders (Dashboard, Slides, Excel).
  - Renamed flag `HYBRID_SLIDE_DECK` → `HYBRID_ONECLICK_ARTIFACTS` (DB override migrated for org 55278108). `routes/report_slides.py` generalized: shared `_generate_artifact(mode)` helper + `POST /api/reports/{id}/dashboard/generate` (mode=page) alongside the slides one; both run the chat `create_artifact` pipeline over the report's existing vizs, delete their own artifact on failure. New read-only `GET /api/reports/{id}/workbook` returns one sheet per query's latest success step (parquet-hydrated `steps.data`, capped 5000 rows × 50 sheets) — the `/api/queries` list strips step rows so the Excel tab couldn't build client-side.
  - FE `pages/reports/[id]/index.vue`: dashboard CTA branch before `ArtifactFrame` (gated `oneClickEnabled` + `!hasPageArtifact` + has vizs); `excelSheets` now prefers `serverSheets` (fetched from `/workbook` on load) over the message-scraped fallback; `generateDashboard()` mirrors `generateSlideDeck()`. Flag read renamed to `HYBRID_ONECLICK_ARTIFACTS`.

## v1.38.0 — One-click slide decks with real charts  (2026-06-27)
- A report's **Slides** view now has a **Generate slide deck** button: turn the report's charts into a polished PowerPoint-style deck — with real charts, not placeholders — in one click, no chatting required.
- The deck is a proper presentation you can **export as .pptx**, and it shows real chart previews instead of the old grey placeholder boxes.
- Decks no longer break on mixed data: single-number KPIs and charts without categories are handled gracefully instead of failing the whole deck.
  - New flag `HYBRID_SLIDE_DECK` (default OFF, ON org 55278108) gates `POST /api/reports/{id}/slides/generate` (`routes/report_slides.py`) + the FE button. The endpoint reuses the chat `create_artifact` slides pipeline standalone (org default model + minimal runtime_ctx) over the report's existing visualizations → real `Artifact(mode='slides')` with pptx + preview PNGs → `ArtifactFrame`. FE: `pages/reports/[id]/index.vue` slides fallback now shows the button (flag ON) instead of the `SlidesPanel` placeholder; on success it refetches artifacts so `hasSlidesArtifact` flips.
  - Fixed two pre-existing slides-pipeline bugs surfaced by the standalone path: the pptx sandbox AST gate forbade `getattr`/`hasattr` (which the prompt's own mandatory `style_chart_text` helper uses) → whitelisted read-only in `pptx_executor.py`; and decks crashed with "chart data contains no categories" on KPI/empty-category vizs → added a mandatory DATA SAFETY rule to the slides prompt (filter empty labels, render KPI/text slide instead, per-chart try/except). Route deletes its own failed artifact so a failed attempt leaves no stale empty deck.

## v1.37.0 — Scheduled reports, emailed clean  (2026-06-26)
- Each agent now has a **Reports** tab: schedule it to run on a cadence (daily / weekly / monthly) and email the result to whoever you choose — sent from the agent's own email identity.
- The email is clean and readable: a real result table with the agent's key insights, a full **dashboard as an inline picture plus an attached PDF**, a generated deck or document as a preview with the file attached, or a workflow run's step-by-step outcome — whichever fits the report.
- No more raw chat dumps: the planning notes, draft tables and tool code that belong in the chat window are stripped out, so recipients get a tidy report.
- A "Send test now" button delivers one immediately so you can check it before it goes live.
  - New universal delivery layer `backend/app/services/report_delivery/` (frozen `contract.py`: DeliveryContext/Parts + renderer registry + async DB-aware `classify`; `extract.py` sanitizer + structured-result/SQL extractor; `template.py` shared skeleton/table/insights; `assembler.py` classify→render→send with transient-DNS retry + inline-cid path; `renderers/` auto-imported: `result` P1, `dashboard` P3 Playwright PNG+PDF via `render_service.py`, `artifact` P4 poppler/soffice preview, `workflow` P5 timeline).
  - `notification_service.send_scheduled_prompt_results` rewired to the rich path under flag `HYBRID_RICH_REPORT_EMAIL`; legacy raw-content path kept when OFF. `report_format` threaded from the scheduled prompt → `classify` (auto|table|dashboard|artifact|workflow).
  - Studio **Reports** tab gated by `HYBRID_AGENT_REPORTS`: `routes/studio_reports.py` (list/create/update/delete/run-now, reuses ScheduledPromptService; hidden per-studio container report via `report_type='scheduled_container'` marker + `report_service.create_report(studio_id)` so pinned data sources apply) + `components/studio/StudioReports.vue`.
  - Inline cid images added to `email/message_builder.build_email` (multipart/related). Workflow run delivery hook in `routes/workflows.py` (opt-in `notify`).
  - FIX: `email_client_resolver.uses_smtp_config` was missing `studio_smtp` → per-agent sends via `_resolved_send` silently fell back to the (absent) global client. Per-agent SMTP (e.g. an agent on Office 365) now actually sends.
  - Both flags default OFF; ON for org 55278108. Unit tests `backend/tests/unit/test_report_delivery.py`.

## v1.36.0 — Browse SharePoint / OneDrive with your own sign-in  (2026-06-26)
- A super-admin connects SharePoint (or OneDrive) once for the whole org. Each person then signs in with their own Microsoft account and browses only the files they're allowed to see — Microsoft enforces the boundary, so everyone gets their own folder with no extra setup.
- It's a real file browser: open folders, search, tick the files you want, and "Use selected" pulls them in as data you can query or hand to an agent.
- Nobody has to create their own connector, and the admin never sees anyone's personal files.
  - Flag `HYBRID_FILE_BROWSER` (default OFF, per-org). Enabled for org `55278108` in this ephemeral deploy.
  - Built ON TOP of the connector machinery that already existed: `GraphDriveClient` (Microsoft Graph list/read/search), per-user OAuth (`routes/connection_oauth.py` authorize/callback, PKCE+signed state), per-user Fernet token store (`UserConnectionCredentials`) + auto-refresh, and the `sharepoint`/`onedrive` registry entries (`is_document_based`, `data_shape="files"`, `service_principal`+`oauth` auth variants). Isolation = each request builds the client via `connection_service.construct_client(db, conn, current_user)` → the caller's own delegated token → the source's own ACLs.
  - New `app/routes/connection_files.py` (mounted `main.py` `prefix="/api"`): `GET /api/connections/{id}/files?folder_id=&q=` → `{items:[{id,name,is_folder,mime_type,size,modified_at,web_url}],folder_id}`; `POST /api/connections/{id}/files/ingest` body `{file_ids,studio_id?,data_source_name?}` → `{ingested:[{file_id,data_source_id,name}],errors:[]}`. Flag-gated 404; 400 if connector not file-based; **409 `{"error":"connect_required"}`** when the user has no token (FE shows sign-in); Graph errors fail-soft 502. Ingest reuses `file_service.upload_file` + `create_data_source_from_file` (greenlet-safe) + optional `StudioDataSource` pin.
  - Added two methods to `graph_drive_client.py`: `list_children(folder_id)` (returns BOTH subfolders and files with `is_folder` — the existing `list_files`/`_walk` drop folders, so navigation needed this) and `read_file_bytes(file_id)` → `(name, raw_bytes)` for the ingest lane (existing `read_file` returns parsed DataFrames, not raw bytes).
  - Frontend `components/connectors/FileBrowserModal.vue` (sign-in state reuses the existing `GET /connections/{id}/oauth/authorize` → `window.location = authorization_url` trigger from `UserDataSourceCredentialsModal`; breadcrumb nav by `folder_id`, debounced search, folder/file rows, "🔒 your files only", "Use selected → ingest"). Mounted in `components/ConnectionDetailModal.vue` via a "Browse files" button shown only for `type ∈ {sharepoint,onedrive,google_drive}` (explicit-imported to dodge the `<ConnectorsFileBrowserModal>` auto-import landmine).
  - VERIFIED (no live Microsoft creds): flag effective ×workers, 400 on a non-file connector, **409 connect_required** on a SharePoint connector with no user token, `oauth/authorize` returns a real `login.microsoftonline.com` URL (Files.Read.All/Sites.Read.All + PKCE state), ingest-without-token 409. True end-to-end sign-in needs a real Azure app reg + `PUBLIC_URL` redirect (local base_url is `0.0.0.0:3000`).

## v1.35.0 — Private connectors per agent (only the creator can see or use them)  (2026-06-26)
- Each agent can now have its own private data connectors. Open an agent → Connectors → "New private connector", pick a type (PostgreSQL, MySQL, Snowflake, MS Fabric, REST API, CSV), enter the connection, test it, and it's pinned to that agent.
- A private connector belongs only to you. Other people you invite to the agent can chat with it, but they can never see its credentials, settings, or tables — and it can't be shared, made public, or reused in another agent.
- Delete the agent and its private connectors (and their stored secrets) are removed with it.
  - Flag `HYBRID_AGENT_CONNECTORS` (default OFF, per-org override via Settings → Feature Flags). Enabled for org `55278108` in this ephemeral deploy.
  - Decisions: creator-only (NO admin bypass on owned connectors) · created inside the agent (studio_id-bound) · cascade-delete on owner/agent removal.
  - Backend: two nullable cols on `connections` — `owner_user_id` (FK users.id, indexed) + `studio_id` (FK studios.id ON DELETE CASCADE, indexed). NULL/NULL = org-wide connector (byte-identical to before). Migration `agentconn1` (down_revision `usergroups1`; new alembic head). New `app/services/private_connector_guard.py` (feature gate 404, `is_private`/`owns`/`require_owner` 403 no-admin-bypass, `deny_share`/`deny_share_data_source`, `filter_visible`, `teardown_private_connection`). `routes/connection.py`: owner-filter on list + `require_owner` on get/update/delete/test/refresh/reindex/refresh-tools/tools/query-identity + read paths. `routes/rbac.py`: `create_resource_grant` 403s a private connection (or a DataSource wrapping one). `services/data_source_service.py`: `add_data_source_member` + `update_data_source` block share/is_public on a private-connector-backed DS. `routes/studio_sources.py`: `POST/GET /api/studios/{id}/connectors` + `PUT/DELETE /api/studios/{id}/connectors/{conn_id}` (flag-gated 404, owner/editor via `_require_role`, private+owned+studio-bound enforced; create auto-wraps a private `DataSource(is_public=False, owner_user_id)` + links via `domain_connection` + pins `StudioDataSource`; empty-credentials PUT preserves the stored secret). `routes/studio.py` `delete_studio` reuses `teardown_private_connection`.
  - Frontend: `components/studio/StudioConnectors.vue` (private cards 🔒 "Owned by you · not shareable", org cards read-only, create modal = 6-type picker + lock banner + Test + "Create & pin to agent", per-card Test/Edit/Reindex/Delete, NO share/members/make-public). `pages/studios/[id]/index.vue`: explicit import + flag-gated "Connectors" Build tab. Reads flag from `GET /organization/hybrid-flags` row `env_name==HYBRID_AGENT_CONNECTORS`.`effective`, fail-soft. Bare useMyFetch paths.
  - LANDMINE: teardown of a *schema-indexed* private connector must delete in FK-safe order — `StudioDataSource` pins → `datasource_tables` (column is `datasource_id`, no underscore; refs `connection_tables`) → `domain_connection` link → wrapping `DataSource` → flush → `db.delete(connection)` (ORM cascade then clears `connection_tables`/`user_credentials`/`user_tables`/`connection_tools`/`user_tools`/`indexings`). Deleting the connection first 500s on `connection_tables_connection_id_fkey` / `fk_datasource_tables_connection_table_id`. Found + fixed during live smoke (129 connection_tables rows).
  - LANDMINE (reconfirmed): 4 uvicorn workers, no --reload — restart `ca-app` after toggling the flag so `load_overrides_from_db` re-applies the DB override to every worker.

## v1.34.0 — My Groups: user-owned contact groups + member/group share picker  (2026-06-26)
- Any member can now build their own contact groups under Settings → Access & Members → "My Groups": name a group, search and add people, and reuse it as a one-click share target. Your groups belong to you and show up wherever you share an agent or report.
- New "Add members" picker (like a contact chooser): search people and groups, tick what you want, see your picks as removable chips, and add them all at once. It lists your own groups first, then org groups, then people.
- The members area is now titled "Access & Members" (was just "Access").
  - Flag `HYBRID_USER_GROUPS` (default OFF, per-org override via Settings → Feature Flags). Enabled for org `55278108` in this ephemeral deploy.
  - Backend: `groups.owner_user_id` (nullable FK users.id, indexed) — NULL = org/LDAP group (unchanged), set = user-owned. Migration `usergroups1` (down_revision `agentchan1`). New router `app/routes/me_groups.py` (`GET/POST/PATCH/DELETE /api/me/groups`, `POST/DELETE …/members`, `GET /api/me/contacts`), service `app/services/me_groups_service.py`, schema `app/schemas/me_groups_schema.py`; mounted in `main.py` after rbac. All endpoints gated by the flag (404 feature.locked when off) + owner-enforced (403 via `_get_owned_group`); creator auto-added as member; `(organization_id, name)` unique kept → 409 on collision; `shared_count` = ResourceGrant rows where principal_type=group (so user groups are already valid share principals — no share-flow change).
  - Frontend: `components/ContactGroupPickerModal.vue` (props modelValue/organizationId/multiple/selectedIds/excludeIds/mode/title; emits confirm `{userIds,groupIds}`), `components/MyGroupsManager.vue` (self-gates on `HYBRID_USER_GROUPS` effective, fail-soft). `pages/settings/members.vue`: new flag-gated "My Groups" inner tab. `locales/en.json`: `settings.membersTab` → "Access & Members". Bare useMyFetch paths (baseURL `/api`).
  - LANDMINE: uvicorn runs 4 workers with no --reload — `set_override` via the admin PUT only mutates ONE worker's memory; the flag gate then flickers per-worker (some 200, some feature.locked). Fix = restart the container so `load_overrides_from_db` (main.py:430) re-applies the persisted `config['hybrid_overrides']` to every worker. Always restart after toggling a hybrid flag in a multi-worker deploy.

## v1.33.1 — Settings layout flush + rail dedupe + LLM two-section split  (2026-06-26)
- The Settings pages now sit flush against the left menu with the same even gap as every other page (they used to float centered with a big empty band between the menu and the panel).
- The Settings menu no longer shows "Integrations" twice — Channels, Folder Sync and SMTP are now grouped together under one Integrations heading.
- The LLM settings page is split into two clear sections: "Preconfigured" (the ready-to-use models we ship) and "Your models" (anything you connect with your own provider and key).
  - `layouts/settings.vue`: dropped `flex justify-center`/`max-w-7xl`/`items-center` → standard page shell (`bg-[#F1ECE3] h-full overflow-hidden flex flex-col` + card `my-2 me-2 flex-1 overflow-y-auto`) so the card is flush after AppRail.
  - `useAppNav.ts`: reordered `settingsTabs` so `smtp` sits next to `integrations`/`folder-sync` → the section eyebrow no longer repeats (eyebrow renders on section *change*; SMTP after the SECURITY group caused a 2nd INTEGRATIONS header).
  - `components/LLMsComponent.vue`: `preconfiguredModels`/`customModels` computeds split by `isPreconfigured = is_default || is_small_default || model_id ∈ PRECONFIGURED_MODEL_IDS` (the seed_openrouter.py set: haiku-4.5, sonnet-4.6, sonnet-4, gpt-4o-mini, gpt-5.4-mini). Two band-pill section cards; custom section shows a dashed add-state when empty. FE-only split — keep the id set in sync with the seed, or add a backend `is_preconfigured` flag for durability.

## v1.33.0 — Overview design + studio-scroll across the app, report panel polish  (2026-06-26)
- Every Build, Manage and Settings page (plus all Workspace tabs and Monitoring) now wears the same Overview look — serif title, rounded cream card, section cards and toolbars — so the whole app reads as one design.
- The left menu and page card now scroll like the Agent Studio: the menu stays put with its own scroll, the page scrolls inside its rounded card, and there's an even 8px gap on every side that never disappears. The menu card also fills the full height instead of stopping short.
- Follow-up question chips under a report now fit their text, line up on the left, wrap long questions onto multiple lines, and are never cut off — in both the split view and the docked view.
- The report's Outputs panel shows three cards per row (Dashboard · Report · Slides · Excel · Infographic · Insight Map) with Forecast and Anomaly as "Soon" cards, and the data-source list scrolls on its own so the whole panel fits one screen.
- Opening a dashboard or infographic in full screen now fills the screen instead of showing a tiny card in the corner.
- The artifact toolbar auto-fits — the version picker shrinks and the Share button stays visible instead of being clipped.
  - Reskin: subagent-applied Overview shell to `pages/{knowledge,memory,queries,evals,workflows}/index.vue`, `pages/{instructions,skills,connectors}.vue`; settings via `layouts/settings.vue`; monitoring via `layouts/monitoring.vue`. Lane accents per page.
  - Studio-scroll parity: `layouts/default.vue` right wrapper `overflow-y-auto`→`overflow-hidden`; each page root `min-h-full`→`h-full overflow-hidden flex flex-col`, card `flex-1`→`flex-1 overflow-y-auto`. `AppRail.vue` aside `h-full`→`self-stretch min-h-0` (replaced-flex collapse fix → full-height rail). Build/Manage/Settings got `railHeader` + per-item `section` in `useAppNav.ts` to trigger the studio card rail.
  - `ConsoleInstructions.vue` gained a `fill` prop (`h-[calc(100vh-100px)]`→`h-full min-h-0`) so it fills the page card; `pages/instructions.vue` drops the duplicate band-pill wrapper.
  - Follow-up chips: report chat root gets an always-on `.chat-pane` class; lifted the dock guards (`min-width:0`, `overflow-wrap`, table in-block scroll, `.dock-followups` auto-fit/left/wrap) from `.dash-dock`-only to `.chat-pane` so split view gets them too (`pages/reports/[id]/index.vue`).
  - Outputs panel: `grid-cols-2`→`grid-cols-3`, badges absolute, Forecast/Anomaly promoted to in-grid SOON cards; data-sources list `max-h-[150px] overflow-y-auto`.
  - `ArtifactFrame.vue`: fullscreen iframe `absolute inset-4 w-auto h-auto`→`w-full h-full` (iframe is a replaced element → `width:auto` ignored insets → collapsed to intrinsic 300×150). Toolbar `min-w-0`/`flex-1` on selector, `shrink-0` on action group → no Share clipping.

## v1.32.1 — Workspace Overview framing fix  (2026-06-26)
- The Workspace Overview now sits in its own rounded panel — matching curved corners, a soft border and an even gap on every side — so it pairs cleanly with the left menu instead of running flush to the window edge.
  - `pages/workspace/index.vue` root wrapped in the studio-main card (`my-2 me-2 px-6/8 py-6 bg-[#FBFAF6] border border-[#E9E0D3] rounded-2xl min-h-[calc(100%-1rem)]`) on a `#F1ECE3` cream gutter; removed the old `max-w-[1180px]` left-align that left a dead right gap. Full all-tabs design mock at `scratchpad/workspace-all-tabs.html` (Overview/Templates/Reports/Dashboards/Presentations/Spreadsheets/Scheduled).

## v1.32.0 — New Workspace Overview (Auto-pilot design)  (2026-06-26)
- Workspace now opens on a clean Overview that mirrors the agent Auto-pilot look: a quick "Create" row (new report · dashboard · import), your work organized into four colour-coded lanes (Reports · Dashboards · Presentations · Spreadsheets), and a Library & Schedule row (templates + scheduled). Everything you make shows up here automatically.
  - New `pages/workspace/index.vue` (readiness-style ring + `#2B2A26` numbered band pills + gradient create cards + 4 tinted lanes `#E7F1EB/#E4F0F4/#ECEAFB/#F6EEDD`, copied from the studio Auto-pilot tokens). Fail-soft fetch from existing endpoints (`/reports`, `/reports?has_artifacts=yes`, `/api/artifacts/presentations`, `/templates`, `/scheduled-tasks`). Added `overview` nav item (first in the Workspace group → `/workspace`).

## v1.31.1 — New brand logo across the app  (2026-06-26)
- The new circular City Holdings mark replaces the old gradient square — top nav (every page), login header, and the browser-tab favicon. Text stays "City Agent Insights".
  - Cropped icon from source → `public/assets/logo-mark*.png` + `logo-128.png` + `favicon.ico`/`favicon-32.png`/`apple-touch-icon.png`; TopNav `.cag-mark` + login header swapped CSS-gradient → `<img>`; favicon links added in `nuxt.config.ts`.
  - Dockerfile durable fix: frontend builder now uses `node:22-bookworm-slim` instead of the nodesource curl|bash apt install — kills the #1 cold-build failure (network download + OOM-from-apt). Fast FE deploy: host `yarn generate` + `docker cp .output/public/. ca-app:/app/frontend/dist` (ephemeral, no image rebuild).

## v1.31.0 — Identity Provider: one unified, add-driven list  (2026-06-26)
- The Identity Provider page is now one clean list. Nothing is preset — you start empty and click "Add provider" to add Google, Microsoft, Okta, Keycloak, any OIDC, an LDAP / AD directory, or SCIM provisioning. No more rows sitting there disabled.
- "Add provider" sits at the top-right; LDAP and SCIM are added the same way as everything else.
- Every entry has the same controls: Configure, an on/off switch, and remove.
- Removing a provider now asks for confirmation (tick "I understand this can't be undone") so you can't delete one by accident.
- A "Save changes" button applies your on/off switches and auth-mode choice — flip things freely, then Save once. "Unsaved changes" shows when there's something to save.
- Removed the public sign-up toggle (no open registration from this page).
  - `pages/settings/identity-provider.vue` full rewrite → one `methods` computed merging kinds google/oidc/ldap/scim (only existing/added items shown). Add → `IdpProviderLibraryModal` (now 3 groups via `IDP_TEMPLATES.group`: social/directory/provisioning) → per-type config modal (Google `/sso/google`, OIDC `/sso/oidc` full-list, LDAP `LdapDirectoryModal`→`/enterprise/ldap/directories`, SCIM `useScimTokens`). Configure saves immediately; enable/disable + auth-mode are STAGED → `save()` batches PUT sso/oidc + sso/google + changed ldap dirs + sso/auth-mode, then reloads + clears dirty. Delete = double-confirm modal. Explicit imports (idp/ auto-import prefix landmine). Dropped the 4 fixed default rows, separate SCIM + LDAP sections, `useLdapSync`/single-`ldapForm`, public-signup. No backend change.

## v1.30.2 — Fix: LDAP directories panel now actually shows  (2026-06-26)
- The "LDAP / AD Directories" configuration (add/list/test directories) was invisible — now it renders under the LDAP Directory Sync section.
  - Root cause: Nuxt auto-imports `components/idp/*` with an `Idp` prefix, so `LdapDirectoriesPanel.vue`/`LdapDirectoryModal.vue` registered as `IdpLdapDirectoriesPanel`/`IdpLdapDirectoryModal`; the bare `<LdapDirectoriesPanel>` / `<LdapDirectoryModal>` tags resolved to nothing and rendered empty. Fix: explicit imports in `identity-provider.vue` and `LdapDirectoriesPanel.vue`.

## v1.30.1 — Removed the floating assistant robot  (2026-06-26)
- The floating robot widget in the bottom-right corner is gone from every screen.
  - Removed the global `<RobotAssistant />` mount (`app.vue`) and the `<AgentThinking />` mount + import (`layouts/default.vue`). Components left in the repo, just no longer rendered; activity-store mirrors that fed them are harmless no-ops.

## v1.30.0 — Multiple LDAP / AD directories + username login  (2026-06-26)
- You can now connect more than one LDAP / Active Directory — add as many directories as you need, each with its own enable switch, Test connection, and Delete.
- Sign-in setup is simpler: the default form asks only for the essentials (directory name, host, port, bind DN, bind password, base DN, user filter, email & name attribute). Everything else is tucked under "Advanced".
- Users sign in with their directory username (e.g. the `{username}` in your user filter, like sAMAccountName) — not only their email.
  - Storage: `config['ldap_directories']` list (each: id, name, enabled, logo, host, port, bind DN, Fernet bind pw, base DN, user_filter, email/name attr + advanced). Legacy single `config['ldap']` auto-migrates to one directory (id "default", host/port/ssl parsed from its url); legacy key left intact.
  - Backend: `find_user_by_username` ({username} filter, `escape_filter_chars`); `_build_server` host/port path; `get_effective_ldap_directories()` (DB-over-file, own session); login (`UserManager._do_authenticate`) iterates all enabled directories — username-first, email fallback, first success wins, all-unreachable → local break-glass, binds with the directory's email. Routes `GET/POST/PUT/DELETE/POST-test /api/enterprise/ldap/directories[/{id}]` (EE-gated, manage_identity_providers). Passwords never returned (`bind_password_set` flag).
  - Frontend: `components/idp/LdapDirectoriesPanel.vue` (multi-directory list, per-row toggle/test/configure/delete + "Add LDAP / AD directory") + `LdapDirectoryModal.vue` (DocSensei-style default fields + Advanced collapsible). Replaces the single-LDAP row/modal in `identity-provider.vue`.

## v1.29.1 — Fix: LDAP / Active Directory login now actually uses your saved settings  (2026-06-26)
- LDAP sign-in was ignoring the directory you configured in Settings, so logins always fell back to local accounts. It now uses the saved LDAP/AD connection — directory users can sign in.
- LDAPS (secure) servers now connect correctly based on the server URL (ldaps://), even without a separate SSL switch.
  - Root cause: login (`core/auth.py`) read the static file config `settings.dash_config.ldap`, while the admin UI saves LDAP into `OrganizationSettings.config['ldap']` (DB). Admin "Test connection" worked (it read the DB), but actual login never did → `enabled` was always False → straight to local auth.
  - Fix: new `get_effective_ldap_config()` resolver (DB-over-file, own session, fail-soft) in `organization_settings_service.py`; `UserManager._do_authenticate`/`_ldap_authenticate` (core/auth.py) now resolve and pass the effective config instead of reading the file directly.
  - `LDAPConnectionManager._build_server` derives `use_ssl` from the URL scheme (ldaps:// → SSL, ldap:// → plain) since the modal has no SSL toggle — avoids the ldap3 "full ldaps:// URL + use_ssl=False" conflict that silently failed.

## v1.29.0 — Identity Provider: brand logos, on/off toggles, and a provider library  (2026-06-26)
- Every sign-in method (Google, Microsoft, Okta, Keycloak, OIDC, LDAP) now shows its real brand logo, on the settings page and on the login screen.
- Each method has a simple On/Off switch right in the list. Turn one on even before it's fully set up — it just shows an "On · Needs setup" note, and the login button errors politely until you finish.
- Okta and Keycloak are now ready-to-use options out of the box, and a new "Add provider" library lets you pick from Auth0, OneLogin, Ping, JumpCloud, AD FS, and more — each pre-filled so setup is faster.
- When configuring any connector (LDAP included) you can choose its logo from a built-in set or upload your own.
  - New `frontend/utils/idpLogos.ts` (preset brand SVGs + `idpLogoSvg`), `utils/idpTemplates.ts` (`IDP_TEMPLATES` catalog), `components/idp/IdpLogoPicker.vue` (v-model, preset grid + ≤300 KB upload→data URL), `components/idp/IdpProviderLibraryModal.vue` (`:open`/`@close`/`@select`).
  - `pages/settings/identity-provider.vue`: rows rebuilt as a `ssoRows` computed (Google · Microsoft · Okta · Keycloak defaults · custom OIDC) with logo + smart 4-state pill (`pillText`/`pillClass`) + inline quick-toggle (saves immediately) + library "Add provider"; logo picker added to every config modal. Okta/Keycloak/library picks flow through the existing shared OIDC modal (prefilled from a template); no bespoke modals.
  - `pages/users/sign-in.vue`: buttons render `idpLogoSvg(logo)` per provider (custom upload wins over brand default).
  - Backend: `logo: str` persisted on Google/OIDC/LDAP (`_clean_logo` = preset key OR `data:image/…` ≤400 KB, fail-soft ""), surfaced via `/sso` + `/api/settings` (`google_oauth.logo`, `oidc_providers[].logo`, `ldap_logo`). SCIM has no config object → no logo (cosmetic preset only).

## v1.28.0 — Login page shows only the sign-in methods you've enabled  (2026-06-26)
- The Google, Microsoft, SSO, Keycloak, and LDAP buttons on the login page now appear only when an admin has turned that method on in Settings → Identity Provider. Disabled methods are hidden — no more dead buttons.
- If you turn every external method off, the login page cleanly shows just the email/password form.
  - `/api/settings` now returns `ldap_enabled` (new `get_effective_ldap_enabled()` — DB org config overrides file, fail-soft False). Google + Microsoft + Keycloak already came through `oidc_providers` (Microsoft/Keycloak are stored as OIDC providers).
  - `pages/users/sign-in.vue`: per-button `v-if` on enabled state (`showGoogle/showMicrosoft/showKeycloak/showSSO/showLdap`); social + enterprise rows use dynamic `repeat(N,1fr)` columns so remaining buttons stay full-width; "OR CONTINUE WITH" divider + enterprise box hide when empty. No auth-logic change — authorize endpoints still enforce server-side.

## v1.27.0 — Tidier card buttons on Decks and Dashboards  (2026-06-26)
- The Open / Chat buttons on deck cards no longer wrap onto two lines — they sit flat and are the same size.
- The Chat / Dashboard buttons on dashboard cards are now exactly the same width.
  - Presentations cards (`pages/presentations/index.vue`): shortened labels (Open & generate → Generate, Open in chat → Chat), added `whitespace-nowrap` + `box-border` + `min-w-0` so the two-column grid buttons stay single-line and equal.
  - `components/home/RecentReportCard.vue` (Dashboards + Home grids): button CSS `flex: 1 1 0; width: 0; box-sizing: border-box; white-space: nowrap` so the bordered ghost and borderless primary render identical width.

## v1.26.0 — Channels: use the org default or a custom connection  (2026-06-26)
- For every channel (Slack, Teams, WhatsApp, AI Mailbox, Telegram, MCP) you can now choose: use the organization's shared connection, or set up a custom one just for this agent — same choice you already have for Email.
- Channels default to the organization's connection, so an agent works out of the box with nothing to configure. Switch to "Custom for this agent" only when you want its own app, bot, or number.
- Removed the confusing "locked" message — replaced with a clear note that, whichever connection you pick, every channel still answers only from this agent's data.
  - `components/studio/StudioChannels.vue`: per-platform mode radio (global vs custom). Mode derived from data — a per-studio channel row = custom, none = org default; local override lets the user flip to custom before a row exists. Global branch shows an org-default note + "Remove custom" revert; custom branch keeps Set up/Reconfigure/Enable/Disable/Delete. Status chip is mode-aware (Org default / Connected / Not connected). No backend change — relies on existing NULL studio_id → org fallback.
- The "What's new" notes are now written in plain language instead of developer shorthand, so anyone can understand what changed.
- Curious about the deep technical details of a release? They're tucked under a "Technical details" toggle on the full What's new page.
  - Changelog parser (`backend/app/services/changelog.py`) splits bullets: top-level `- ` → `features` (user-facing, shown in popover), indented `  - ` → `details` (technical, hidden from popover).
  - Full page `pages/changelog/index.vue` renders `details` under a collapsed `<details>` toggle. Popover `WhatsNew.vue` unchanged (already renders `features` only). Recent entries (v1.20–1.24) rewritten plain + technical detail moved to indented bullets.

## v1.24.0 — Connect each agent to its own channels and email  (2026-06-26)
- Each agent now has its own Channels tab. Connect Slack, Teams, WhatsApp, an AI Mailbox, Telegram, or MCP to a single agent — pick a platform on the left, set it up on the right. Turn any channel on or off without touching your other agents.
- Each agent now has its own Email / SMTP tab. An agent can send its emails (shared results, scheduled reports, replies) using the company default, or you can give it its own mail server. A one-click "send test" confirms it works before you rely on it.
- The agent's left menu is now split into Access & Members, Channels, and Email / SMTP, so settings are easier to find.
- App updates ship faster — rebuilds are quicker behind the scenes.
  - Channels UI: `components/studio/StudioChannels.vue` — org-style two-pane picker (platform list + detail pane), reuses the Slack/Teams/WhatsApp/AI-Mailbox modals + Telegram/MCP. Per-platform status dot + set-up/reconfigure/enable/disable/delete, scoped to the studio.
  - Email UI: `components/studio/StudioEmail.vue` — mode radio (global default vs custom), custom fields mirror org SMTP (host/port/security/user/pass/from/validate-certs) + test. Stored in `Studio.config['smtp']` (Fernet password), no migration.
  - Backend: `email_client_resolver` per-agent SMTP tier (`get_studio_smtp` + `studio_smtp` precedence in `choose_outbound`; `resolve_outbound(..., studio_id=)`) wins over org/global. Routes `GET/PUT/POST-test /api/studios/{id}/smtp` (flag `HYBRID_AGENT_CHANNELS`, owner/editor). `studio_id` threaded through `notification_service`, `report.py` share, `email_send_service` replies. NULL studio / global mode = unchanged.
  - Dockerfile: dropped non-deterministic `apt-get upgrade -y` from builder stages (cache-stable); BuildKit cache mounts for Vite/Nuxt transform caches on `yarn generate`. Runtime `base` stage keeps its security upgrade.

## v1.23.0 — Faster dashboards on big results + agents answer in chat apps  (2026-06-26)
- Big result tables now load faster and take up far less storage, so dashboards built on large queries open quicker.
- Filter, sort, and page through large results live — only the rows you're looking at are fetched, even on millions of rows.
- Agents can now answer in Slack, Teams, WhatsApp, an AI Mailbox, Telegram, or MCP. A question coming from a channel is automatically answered using only that agent's data.
  - Parquet result storage: `backend/app/services/parquet_store.py` — results ≥`HYBRID_PARQUET_MIN_ROWS`=2000 rows offload to compressed Parquet on the `ca_uploads` volume instead of inline JSON in Postgres. Transparent hydrate on read; flag `HYBRID_PARQUET_RESULTS` default ON; crash-safe, fail-soft, daily purge GC. Docs: `docs/parquet-results.md`.
  - Interactive query endpoint `POST /steps/{id}/query`: allow-listed DuckDB pushdown (filter/group/agg/sort/page), returns slice + true total_rows, no raw SQL, limit cap 5000. Frontend `useStepQuery` + dashboard routes for `source:"parquet"` steps; inline steps keep client-side path.
  - Per-agent channels (flag `HYBRID_AGENT_CHANNELS` default ON): per-studio CRUD for all types (upsert, Fernet creds, audience). Inbound webhooks bind the report to the matched channel's `studio_id` → ReportService auto-scopes to that studio's sources. NULL studio_id = unchanged.
  - `scripts/safe-upgrade.sh` (NEW): guarded bake — rollback-tag image, backup DB+uploads together, health-gate, auto-rollback on failure.

## v1.22.0 — New look, now everywhere  (2026-06-26)
- The new warm look is now applied across the whole app — reports, chat, agents, monitoring, evals, templates, onboarding, sign-in, files, and shared/embedded pages all match.
- A visual refresh only — nothing about how the app works changed.
  - Completed the warm-palette rollout: 32 remaining pages + 148 components + 3 layouts. Token-only migration: clay→coral (`#C2541E`/`#A8330F`), borders `#E9E0D3`, surfaces `#F4EEE5`, headers → Spectral 32px. Zero icons/logos/logic changed.

## v1.21.0 — New look for Settings  (2026-06-25)
- All Settings screens got the new warm look — Members, Models, AI Settings, General, Integrations, Folder Sync, Audit, Identity Provider, SMTP, Feature Flags, and Analytics.
- A visual refresh only — every setting works exactly as before.
  - Migrated `layouts/settings.vue` + settings-imported components (`sync/FolderSyncPanel.vue`, Email/WhatsApp/Teams/Slack modals). Token-only: clay→coral (`#C2541E`/`#A8330F`), borders `#E9E0D3`, surfaces `#F4EEE5`, Spectral 32px headers.

## v1.20.0 — Simpler navigation + refreshed pages  (2026-06-25)
- Navigation is simpler: the old top dropdowns are replaced by a left side menu that shows just the section you're in.
- Open an agent and refresh — it now stays on the tab you were viewing instead of jumping back to the start.
- Templates, Knowledge, Instructions, Queries, Skills, Memory, Connectors, Evals, and Workflows all got the new warm look.
  - `components/nav/AppRail.vue` replaces top-nav dropdowns; nav model in shared `composables/useAppNav.ts` (TopNav + AppRail). Mounted in `layouts/default.vue` non-report branch; self-hides on pages that own a rail.
  - Studio detail `?tab=` query persists the sub-tab on refresh. Templates restyled to Workspace v2. Build/Manage warm migration + Spectral headers. (Monitoring console deferred.) Restyle only; data/logic/permissions unchanged.

## v1.19.0 — Studio detail retheme + Open/refresh crash fix (bake)  (2026-06-25)
- Rethemed the studio detail/workspace page (`pages/studios/[id]/index.vue`) to the warm design system: cream bg + Hanken body, coral accents (`#C2541E`/`#A8330F`), Spectral serif headings, warm borders (`#E9E0D3`).
- **Fixed studio Open → refresh crash** (`Cannot read properties of null (reading 'name')`): teleported `FolderSyncSetupModal` + `FolderSyncCard` read `studio.name` in a separate reactive scope during the cold-load null window, before `fetchStudio` resolved — not covered by the parent `v-else-if` guard. Added `v-if="studio"` + `studio?.name || ''` on both.
- Bakes durable everything previously shipped via ephemeral FE-sync (studio retheme, crash fix, AgentThinking widget).
- Added `scripts/fe-sync.sh` — host `nuxt generate` + `docker cp` into `ca-app` for FE iteration without a full image rebuild (ephemeral; reverts on force-recreate).

## v1.18.0 — Design system rollout: Studios, Home, Nav, Reports + Agent status widget  (2026-06-25)
- Applied the Claude Design warm palette (cream `#F6F1EA`, ink `#1A1611`, coral `#C2541E`/`#A8330F`/`#D67037`, Spectral serif + Hanken Grotesk) across the authed app — restyle only, no functional changes.
- **Studios** (`pages/studios/index.vue` + `components/studio/StudioCard.vue`): cream bg, Spectral 38px header, "YOUR AGENT STUDIOS" label, coral New button. Card → Studios v2 mock: dark live-activity header (gradient + grid-drift + orange blob + animated equalizer on live / dashed "awaiting first source" on draft), white overlapping icon badge, Spectral italic persona, live-stats vs draft/ready progress, coral + ghost action bar. Equalizer + Live dot keep animating under reduced-motion.
- **Home** (`pages/index.vue`): cream bg, orange orb glow, greeting eyebrow, Spectral 46px "What should we *explore* today?", subtitle; dropped purple bottom-glow + full-logo hero. Real composer/suggestions/reports children unchanged.
- **Top nav** (`components/nav/TopNav.vue`): cream translucent bar (blur + `#E9E0D3` border), gradient logo mark + "City Agent Insights" wordmark, warm nav links (active `#A8330F`), cream New-report pill, dark-gradient avatar. Full-width — flush left/right, no side gap. Spectral + Hanken loaded app-wide here.
- **Reports** (`components/home/RecentReports.vue` + `RecentReportCard.vue`): scope dropdown → **segmented tab** (Main Org / My Reports). Cards restyled (badge + Chat/Dashboard buttons) keeping the **real** server thumbnail preview — no fake numbers; no-preview falls back to a mode icon.
- **Agent status widget** (`components/agent/AgentThinking.vue`, global in `layouts/default.vue`): floating coral robot launcher → dark terminal popover typing real boot lines (`synced N sources · M tables` from `/data_sources`, `vector index warm`, `ready.`) with blinking cursor; footer = Idle + real default model from `/llm/models`. Fail-soft, counts warmed in background.

## v1.17.0 — Login page redesign (Claude Design handoff)  (2026-06-25)
- Reimplemented `pages/users/sign-in.vue` pixel-faithful to the Claude Design mock (`City Agent Insights Login.dc.html`). New warm palette (`#F6F1EA` bg, `#C2541E`/`#A8330F` accent), Spectral serif headline + Hanken Grotesk body (loaded via `useHead`), gradient logo mark, floating-label EMAIL/PASSWORD fields with a Show/Hide pill.
- Removed the `4 sources · 11 tables · 67 columns · data 2026-06-20` stat line from the left column (per request).
- ALL auth buttons now present: Google + Microsoft (2-col social row) and a dedicated **Enterprise Sign-in** box with **SSO / Keycloak / LDAP**. Wiring: Google → `/api/auth/google/authorize`; Microsoft/Keycloak/SSO → `signInWithProvider()` matched against the org's configured OIDC providers (regex map, fail-soft message when a provider isn't configured); LDAP → reveals + focuses the directory username/password form (LDAP authenticates through the same `/api/auth/jwt/login`).
- Right panel replaced with an animated "agent at work" showcase: a 3-turn loop (pick data source → live progress checklist → result card with growing bar chart + delta), ported from the design's `DCLogic` state machine to Vue refs + timers, cleaned up on unmount, and disabled under `prefers-reduced-motion`. Hidden below 1024px (single-column form on mobile).
- Version chip stays dynamic (`hybrid_version` from `/api/settings`).

## v1.16.1 — Login version chip is real (was hardcoded v2.4.0)  (2026-06-25)
- Sign-in page chip showed a stale hardcoded `v2.4.0 · local`. Now reads the real product version from `/api/settings.hybrid_version` (= VERSION_HYBRID) and derives the env label from the host (localhost → local, else prod).
- `/api/settings` (public, pre-auth) now returns `hybrid_version` via `changelog.current_version()` — distinct from the upstream-base `version` (PROJECT_VERSION).
- Dockerfile fix: `VERSION_HYBRID` + `CHANGELOG_HYBRID.md` are now COPY'd into the image at `/app/` (final stage). They were never copied, so `current_version()` always fell back to `0.0.0` — this also silently broke the in-app changelog popover. LANDMINE: `app/services/changelog.py` resolves `_REPO_ROOT=/app`; both files must live there in the image.

## v1.16.0 — Feature flags fully UI-owned; ENV is infra-only  (2026-06-25)
- ENV/compose stripped of all ~50 `HYBRID_*` flags + skill-exec knobs + compaction ratio. They now live exclusively in the UI (Settings → Features), persisted per-org in `organization_settings.config['hybrid_overrides']`.
- Defaults are now CODE-owned (`hybrid_flags.py`): 37 product-visible features default ON (Studios, Templates, Folder Sync, Intelligence + Knowledge layer, caches, autotrain, etc.), the rest OFF — so a fresh deploy is fully featured with zero env flags. Previously only `SCOPE_GATE` + `DASH_VERSIONS` defaulted ON and the nginx compose carried the real defaults.
- Resolution order unchanged: per-org override > env > code default. `load_overrides_from_db()` at boot (`main.py:431`) hydrates the process override store from DB — verified live ("Loaded 65 hybrid flag override(s)").
- One-shot migration froze each org's current effective env values into `hybrid_overrides` (org 55278108: 65 overrides, 51 ON) so removing env changed no live behaviour. Pre-existing UI overrides preserved (never clobbered).
- Lean `.env` (~15 vars): DB conn, `DASH_ENCRYPTION_KEY`, `REDIS_URL`, ports, `DASH_CONFIG_PATH`, `DASH_LICENSE_KEY`, `AUTOTRAIN_STAGING_*`, plus bootstrap seeds (LLM key/models via dash-config or UI; super-admin `DASH_ADMIN_*`).
- LANDMINE: do NOT re-add flag vars to compose/.env — they shadow the UI until an org sets an override. New flags get their default in `hybrid_flags.py` (`_bool("NAME", default)`), not in compose.

## v1.15.0 — Hybrid Search is real: embeddings via OpenRouter  (2026-06-25)
- `HYBRID_SEMANTIC_SEARCH` was a scaffold (empty index, no embedder, never wired). It now works end-to-end:
  - **Embedder** (`app/ai/knowledge/embeddings.py`) — reuses the org's existing OpenRouter key (OpenAI-compatible `/embeddings`), model `openai/text-embedding-3-small` (1536-dim → matches the existing `embedding vector(1536)` column, no migration). Batched, fail-soft. Env knobs `HYBRID_EMBED_MODEL/DIM/BATCH`.
  - **Indexer** (`app/ai/knowledge/indexer.py`) — `reindex_org()` rebuilds `knowledge_search_index` from approved semantic tables / metrics / query library / docs, sets the PG `tsv` and the `embedding` vector.
  - **Retrieval** — `hybrid_search()` gained a pgvector cosine-KNN arm; now fuses FTS + vector + token-Jaccard via 3-way RRF.
  - **Wired into the agent** — new `HybridSearchContextBuilder` + section, primed in `context_hub` and appended to the planner instructions in `agent_v2` (gated by SEMANTIC_SEARCH). Top approved knowledge is injected as grounding for each question.
  - **UI + API** — `POST /api/knowledge/reindex` + `GET /api/knowledge/search-index/status`; a "Rebuild search index" button appears on the Hybrid Search row in Settings → Features when it's on.
- Proven live: 293 assets indexed + embedded via OpenRouter (200 OK); "revenue by month" returns Total Revenue / Revenue-by-Country etc. ranked by RRF.
- Flag reclassified `unstable` → `experimental` (works once a key is set). Without a key, only the full-text arm builds (still useful).

## v1.14.0 — All feature flags toggleable from the UI  (2026-06-25)
- Settings → Features now lists **every** hybrid flag (65, up from ~32), grouped into 8 sections (Core, Knowledge, Intelligence, Agents & Access, Ingest, Learning, Advanced, Daemons). Previously most flags — including Agent Studios itself, the caches, semantic/metrics layer, autotrain and the daemons — weren't registered, so they couldn't be toggled from the UI and the override was silently ignored.
- Each flag carries a status badge so risky ones are honest, not silently broken: `needs setup` (Forecast → needs Prophet bake; Federation → needs S3), `unstable` (Skills sandbox can livelock; Hybrid Search is a scaffold), `experimental` (Subagents/token-heavy, Bitemporal, etc.), `needs restart` (the boot-read daemons). Enabling an unstable/needs-setup flag pops a confirm dialog with the caveat.
- Page gained search + an Enabled/Disabled filter and an "N / M on" counter.
- Backend: extended `UPGRADE_FLAGS` with `category`/`status`/`note` per flag (and added every missing flag); `_effective()` now falls back to override-or-env for the env-only daemon knobs (no `flags` property). Same `GET/PUT /api/organization/hybrid-flags` endpoints — no new routes, no migration. Per-org overrides still beat `.env` and apply live (daemons after a restart).

## v1.13.2 — Fix "Sign-up is disabled" when admin creates a user  (2026-06-25)
- Direct user creation hit the fastapi-users registration gate (`_validate_user_creation`), which rejects any non-first signup when uninvited-signups are off → "Sign-up is disabled. Ask your admin for an invite." That gate is the invite flow the admin is explicitly opting out of. Admin-initiated creation now inserts the user directly (hash password + active/verified), bypassing the gate, then attaches the org membership. Mirrors the OAuth path's direct `user_db` create.

## v1.13.1 — Fix blank charts in dashboard full-screen  (2026-06-25)
- Clicking full-screen on a dashboard showed only the static header card with the rest black. The full-screen overlay renders a SECOND iframe, but the data was only ever posted to the background iframe — so the full-screen one rendered its chrome with empty charts. Now `ARTIFACT_DATA` is broadcast to both iframes (background + full-screen), plus a belt-and-suspenders re-send on the full-screen iframe's load. Charts now render in full-screen.

## v1.13.0 — Super-admin creates users directly + features ON in nginx deploy  (2026-06-25)
- Add user with email + password directly — NO email invitation. Settings → Members → "Add user" now takes a name, email and password and creates an active, verified account the user can sign in with immediately. New endpoint `POST /api/organizations/{id}/members/create-user` (admin-gated, `manage_members`); the password is set by the admin and shown in plain text in the form so it can be shared. The old email-invite path still exists for SMTP deployments.
- Fix "Agent Studios are not enabled" (and other locked pages) on the nginx deploy: `docker-compose.nginx.yaml` was missing the `HYBRID_*` env block entirely, so every feature flag fell back to its default-OFF. It now passes the full flag set with product-visible, stable features defaulting ON (Studios, Agent Templates, Folder Sync, per-agent ACL/Channels, follow-ups, semantic/metrics layer, deep profiler, proactive insights, golden queries, verified metrics, query/result/answer cache, domain packs, teach box, agent memory, auto-train, dual-schema/engineer assets, brain read/distiller). Daemons, experimental and token-heavy paths (Skills sandbox, Subagents, Skill Optimizer, Workflows, context compaction, federation, forecasting, all background daemons) stay OFF — enable per `.env`.
- `docker-compose.nginx.yaml` gains a Redis service (`dash-redis`) so the cache-backed features have a backing store; `REDIS_URL` defaults to `redis://redis:6379/0`.
- Apply on the server: `docker compose -f docker-compose.nginx.yaml up -d --build` (rebuilds the image with the new user-create UI/endpoint and recreates the app with flags on). To override any flag, set it in `.env` (e.g. `HYBRID_SUBAGENTS=1` or `HYBRID_STUDIOS=0`).

## v1.12.0 — nginx reverse-proxy stack  (2026-06-25)
- New `docker-compose.nginx.yaml` + `nginx/nginx.conf`: front the app with nginx (the default proxy for this deployment). nginx publishes the host port (`HTTP_PORT`, default 8001) and proxies to the app over the internal network; the app is not exposed directly.
- nginx tuned for this app: SSE streaming (`proxy_buffering off` so chat streams token-by-token), websocket upgrade passthrough, unlimited upload size, 1h read/send timeouts (no 504 on long agent runs).
- Run it: `docker compose -f docker-compose.nginx.yaml up -d --build` → `http://<host>:<HTTP_PORT>`. Set `HTTP_PORT` + `DASH_BASE_URL` in `.env`.
- Caddy stack (`docker-compose.yaml`, auto-HTTPS) and direct-port (`APP_PORT`) paths still available.

## v1.11.1 — Publish app on configurable host port  (2026-06-25)
- The main `docker-compose.yaml` (Caddy/SSL variant) now publishes the app on the host via `APP_PORT` (default 3000) instead of `expose:` only — fixes "app only shows 3000, can't reach my chosen port". Set `APP_PORT=8001` in `.env` to reach it at `http://<host>:8001`. The container always listens on 3000 internally; this maps host→3000.
- `.env.example` documents `APP_PORT` (and that `DASH_BASE_URL` should match it / your domain)
- Caddy front-door path unchanged: for HTTPS you can drop the published port and let Caddy proxy to `app:3000`

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
