# PLAN — Agent Templates (share an agent's best practices, not the agent)

Let a smart agent (Studio) export its **data-agnostic know-how** — rules, metric formulas,
example patterns, skills, persona — as a portable, versioned **template**. Others browse a
**Gallery**, **bind** it to their own columns, and get their own agent. Data, credentials and
values never leave.

Reuses existing machinery: **Domain-Pack bind-gate** (column mapping), **review gate**
(pending→approve), **Skills library** (skill parts), **VERSION/changelog** (semver discipline).
All new work flag-gated `HYBRID_AGENT_TEMPLATES` (default OFF), additive, backups before any core edit.

## Core principle (the contract)
Export the **abstraction + a binding contract**, version it, gate it on import, keep data private.
- Transfers: instructions, example *patterns* (SQL generalized to `{role}` placeholders), metric
  *definitions* (formula+grain), skill refs, persona/voice/summary.
- Never transfers: data sources, credentials, rows/values, org id, members, literal table/column names.
- Bridge: `requires_columns` = list of `{role, as}` (e.g. `TEMPORAL as order_date`). Import maps each
  to the consumer's real column; placeholders `{order_date}` get rewritten.

---

## Phase 0 — schema + format  (foundation; one owner)
- **0a** model `app/models/agent_template.py`: `AgentTemplate` (id, organization_id nullable for
  global, author_user_id, name, slug, version, domain_tags JSON, scope `org|global`, status
  `draft|published`, body_md TEXT, manifest JSON, source_studio_id nullable, created_at). Published
  versions immutable → a new version = new row (same slug, bumped version).
- **0b** migration `agtmpl1` off head `chlogseen1` (verify true head). Guard PG-only DDL.
- **0c** the template file format (md + frontmatter) — document in this file; `manifest` JSON mirrors
  frontmatter for fast querying. Fields: name, version, author, domain, `requires_columns`,
  `uses_skills`, `example_questions`.

## Phase 1 — EXPORT (User A: studio → template)
- **1a** `app/services/templates/exporter.py` (pure-ish, never-raise): given a studio_id, gather
  `studio_instructions` (active) + `studio_examples` + `studio_metrics` (definitions) + `studio_skills`
  refs + persona/voice/summary. **Strip** data/creds/org/member/table-names.
- **1b** generalize: replace concrete column names in example SQL + metric sql_calc with `{role}`
  placeholders, using the studio's `profile_v2` column→role map (Deep Profiler already classifies
  roles). Derive `requires_columns` from the placeholders actually used.
- **1c** emit `body_md` + `manifest`; persist an `AgentTemplate` row (status=draft, version from a
  bump rule). Also return a downloadable `.md`.
- **1d** route `POST /api/studios/{id}/export-template` → `{template_id, version, download_md}`
  (gated `manage` access + flag).

## Phase 2 — GALLERY + publish (storage/discovery)
- **2a** routes `app/routes/agent_templates.py` (registered in main.py):
  `GET /api/templates` (list; scope filter org/global; search by name/domain; read-only, fail-soft),
  `GET /api/templates/{id}` (detail incl. manifest + requires_columns),
  `POST /api/templates/{id}/publish` (draft→published, scope set, version frozen),
  `POST /api/templates/import` (upload a `.md` file → parse → draft row),
  `DELETE /api/templates/{id}` (own drafts only).
- **2b** parser `app/services/templates/parser.py` reuses the changelog/frontmatter idiom; validates
  manifest; never-raise.

## Phase 3 — BIND + instantiate (User B: template → their agent)
- **3a** `app/services/templates/binder.py`: given template + target data_source(s) + a
  `column_map {role/placeholder → real_column}`, rewrite instructions/examples/metrics with the real
  columns. **Auto-match**: propose a column_map by matching `requires_columns` roles against the
  target's `profile_v2` roles (fuzzy on name via `pg_trgm`/token-Jaccard — no embeddings).
- **3b** route `POST /api/templates/{id}/instantiate` body `{name, data_source_ids, column_map}` →
  creates a NEW Studio, seeds bound instructions/examples/metrics as **status='pending'**, attaches
  skills via the existing **pack bind-gate**, sets persona/voice/summary. Returns new studio_id.
  Gated flag + create-studio permission. Fail-soft + transactional.
- **3c** unbound/unsure roles → returned as `needs_user` so the wizard asks (don't guess silently).

## Phase 4 — FRONTEND
- **4a** nav: add `{ key:'templates', href:'/templates', icon:'heroicons-square-3-stack-3d',
  label:'Templates' }` to the **Studios group** in `nav/TopNav.vue` (right after `studios`). Backup.
- **4b** `pages/templates/index.vue` — Gallery: Org/Global toggle, search, template cards
  (name, domain tags, author, ★uses, requires-columns preview), **Use template** + **Publish**.
  Clay/DESIGN_SYSTEM, `useMyFetch` bare paths.
- **4c** `pages/templates/[id].vue` — detail/preview: rules, metric formulas, example questions,
  the binding contract, **Use template** CTA.
- **4d** `components/templates/BindWizard.vue` — 4 steps (pick data → map columns w/ auto-match
  badges → review pending → build). Calls `/instantiate`.
- **4e** **Export entry**: add "✦ Export as Template" to the Studio `⋯` menu
  (`pages/studios/[id]/index.vue`) → export modal (pick what transfers) → calls `/export-template`
  → offer Download + Publish. Backup.
- **4f** **New-agent shortcut**: in `/studios` empty-state + `/studios/new-agent` step 1, add
  "Start from a template" → opens the gallery picker.

## Phase 5 — polish + safety
- **5a** semver bump rule + "new version available" surfacing (ties into changelog version chip).
- **5b** provenance stamp (author/source/version) shown on instantiated items; published = immutable.
- **5c** changelog: add an entry + bump `VERSION_HYBRID` when shipped.
- **5d** docs: CLAUDE/DEVLOG/README + this plan → ROADMAP DONE.

---

## Build order / parallelism
- Phase 0 first (single owner: model + migration + format) — everyone else depends on it.
- Then parallel: **export (1)** ‖ **gallery API (2)** ‖ **bind (3)** are mostly disjoint services;
  share `main.py` (one owner registers the router) + the model (read-only).
- FE (4) after the APIs exist; one owner per file; `TopNav.vue` + `studios/[id]/index.vue` = backup +
  single owner (high-traffic).
- Suggested fan-out (after P0): Agent1 = exporter+generalize (1), Agent2 = gallery routes+parser (2),
  Agent3 = binder+instantiate (3), Agent4 = FE gallery+detail+wizard (4b-4d). Parent = P0, nav +
  studio-menu wiring (4a/4e/4f), register router, flag, backups, verify+bake.

## Risks / landmines
- **Generalization correctness** — wrong column→role placeholder = broken bound SQL. Keep raw golden
  SQL OFF by default; rely on profile_v2 roles; mark low-confidence bindings `needs_user`.
- **Flag registry** — `HYBRID_AGENT_TEMPLATES` needs @property + UPGRADE_FLAGS + snapshot() (else
  per-org override silently ignored).
- **Trust** — imported items MUST land `pending`; never auto-apply a shared template.
- **Global scope** — global templates cross orgs → strip org-specific text hard; review before global publish.
- **Migration** — chain off true single head (`chlogseen1`); watch tuple down_revisions.
- **Nuxt** — new components need explicit imports (path-prefix landmine); restart dev / rebake to show.

## Verify
- import main clean, single head `agtmpl1`, flag-OFF = no nav item + endpoints inert; export a real
  studio → template.md sane; instantiate on a different data source → new agent with pending items
  bound to the right columns; bake FE + commit + changelog bump.
