"""
Hybrid feature flags
====================

Flags that gate the CityAgent Analytics hybrid work (dash patterns +
Karpathy 2nd-Brain + self-service skills + federation). Each maps to an
env var and defaults OFF so a fresh deploy behaves exactly like upstream
dash until a flag is explicitly enabled.

Keep this module dependency-free and decoupled from Settings.load so the
hybrid layers can be toggled without touching core config flow.

Usage:
    from app.settings.hybrid_flags import flags
    if flags.DUAL_SCHEMA:
        ...
"""

from __future__ import annotations

import os


# ---------------------------------------------------------------------------
# Per-process override store (per-org hybrid-flag override layer)
# ---------------------------------------------------------------------------
# When a key is present here it WINS over the env default. Populated at boot
# from organization_settings.config['hybrid_overrides'] (see
# load_overrides_from_db) and kept live by the admin route via set_override.
# Empty by default -> behaviour is byte-identical to the pure-env flags.
_OVERRIDES: dict[str, bool] = {}


def _bool(name: str, default: bool = False) -> bool:
    """Read a boolean flag.

    Resolution order:
      1. process override (`_OVERRIDES[name]`) if present, else
      2. the env var (truthy: 1/true/yes/on, case-insensitive), else
      3. the supplied default.
    """
    if name in _OVERRIDES:
        return _OVERRIDES[name]
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    """Read an integer config knob from env (flags are bool-only; numeric knobs
    read env directly). Falls back to ``default`` on missing/invalid."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


def set_override(env_name: str, value: "bool | None") -> None:
    """Set or clear a per-process flag override.

    value=True/False pins the flag; value=None clears the override so the
    env default takes over again. Takes effect immediately this process.
    """
    if value is None:
        _OVERRIDES.pop(env_name, None)
    else:
        _OVERRIDES[env_name] = bool(value)


def overrides_snapshot() -> dict[str, bool]:
    """Current process override store (copy, for debugging / health)."""
    return dict(_OVERRIDES)


# ---------------------------------------------------------------------------
# Flag registry — drives the Settings → Features UI (per-org override layer).
# Every togglable flag MUST be here or the override is silently ignored AND the
# PUT /organization/hybrid-flags route rejects it. Each entry:
#   label    — human name
#   role     — who the toggle is for: 'agent' (capability) | 'user' (UX) |
#              'review' (writes proposed knowledge through the approval gate)
#   category — UI section grouping
#   status   — 'stable'      : works now, flip to enable
#              'experimental': works but changes behaviour / token-heavy
#              'needs_dep'   : flag alone is not enough (needs infra/bake)
#              'unstable'    : known-bad, keep off
#              'daemon'      : background job, read at boot → needs restart
#   note     — short caveat shown in the UI (optional)
# ---------------------------------------------------------------------------
UPGRADE_FLAGS: dict[str, dict[str, str]] = {
    # --- Core -------------------------------------------------------------
    "HYBRID_STUDIOS": {"label": "Agent Studios", "role": "user", "category": "Core", "status": "stable"},
    "HYBRID_DASH_VERSIONS": {"label": "Dashboard Versions", "role": "user", "category": "Core", "status": "stable"},
    "HYBRID_SCOPE_GATE": {"label": "Scope Guardrail", "role": "user", "category": "Core", "status": "stable"},
    "HYBRID_FOLLOWUPS": {"label": "Suggested Follow-ups", "role": "user", "category": "Core", "status": "stable"},
    "HYBRID_DUAL_SCHEMA": {"label": "Dual Schema (read-only engine)", "role": "agent", "category": "Core", "status": "stable"},
    "HYBRID_ENGINEER_ASSETS": {"label": "Engineer Assets (view builder)", "role": "agent", "category": "Core", "status": "stable"},

    # --- Knowledge --------------------------------------------------------
    "HYBRID_SEMANTIC_LAYER": {"label": "Semantic Layer", "role": "agent", "category": "Knowledge", "status": "stable"},
    "HYBRID_METRICS_CATALOG": {"label": "Metrics Catalog", "role": "review", "category": "Knowledge", "status": "stable"},
    "HYBRID_VERIFIED_METRICS": {"label": "Executable Verified Metrics", "role": "review", "category": "Knowledge", "status": "stable"},
    "HYBRID_GOLDEN_QUERIES": {"label": "Golden Query Promotion", "role": "review", "category": "Knowledge", "status": "stable"},
    "HYBRID_DOC_KNOWLEDGE": {"label": "Company Docs (RAG)", "role": "review", "category": "Knowledge", "status": "stable"},
    "HYBRID_GOVERNANCE": {"label": "Governance (PII/freshness)", "role": "agent", "category": "Knowledge", "status": "stable"},
    "HYBRID_AUTOMAP": {"label": "Auto-configure from Doc", "role": "review", "category": "Knowledge", "status": "stable"},

    # --- Intelligence -----------------------------------------------------
    "HYBRID_PROFILE_V2": {"label": "Deep Profiler (dim catalog)", "role": "agent", "category": "Intelligence", "status": "stable"},
    "HYBRID_PROACTIVE_INSIGHTS": {"label": "Proactive Insights + Anomaly", "role": "user", "category": "Intelligence", "status": "stable"},
    "HYBRID_COLUMN_INTEL": {"label": "Column Intel (pre-train profiler)", "role": "agent", "category": "Intelligence", "status": "stable"},
    "HYBRID_COMPLIANCE_GATE": {"label": "Compliance & Quality Scan", "role": "user", "category": "Intelligence", "status": "stable"},
    "HYBRID_SENSE_MAKING": {"label": "Sense-Making / Decision Layer", "role": "user", "category": "Intelligence", "status": "experimental", "note": "Adds a Decision card (so-what/now-what) above answers. Default OFF."},
    "HYBRID_AUTO_MODEL": {"label": "Auto Model Selection", "role": "user", "category": "Intelligence", "status": "experimental", "note": "Pick 'Auto' in the model picker and a complexity classifier routes each question to the cheapest capable model (Fast/Balanced/Reason). Heuristic first; a cheap LLM tie-break only on ambiguous questions. Fail-soft to the org default. Default OFF."},
    "HYBRID_CODE_ENRICH": {"label": "Code Enrich (pipeline logic)", "role": "agent", "category": "Intelligence", "status": "experimental", "note": "Extra LLM cost on train."},
    "HYBRID_FORECAST": {"label": "Forecasting Tool", "role": "user", "category": "Intelligence", "status": "stable", "note": "Holt-Winters/ETS (statsmodels) + LLM narrative. No heavy dep."},
    "HYBRID_SEMANTIC_SEARCH": {"label": "Hybrid Search (FTS + embeddings)", "role": "agent", "category": "Intelligence", "status": "experimental", "note": "Uses your OpenRouter key for embeddings (text-embedding-3-small). After enabling, click Rebuild search index."},

    # --- Agents & Access --------------------------------------------------
    "HYBRID_AGENT_TEMPLATES": {"label": "Agent Templates", "role": "user", "category": "Agents & Access", "status": "stable"},
    "HYBRID_FOLDER_SYNC": {"label": "Folder Sync (desktop auto-ingest)", "role": "user", "category": "Agents & Access", "status": "stable"},
    "HYBRID_AGENT_ACL": {"label": "Per-Agent Access Control", "role": "user", "category": "Agents & Access", "status": "stable"},
    "HYBRID_USER_GROUPS": {"label": "User-Owned Groups", "role": "user", "category": "Agents & Access", "status": "stable", "note": "Let any member create personal contact groups and use them as reusable share targets (My Groups)."},
    "HYBRID_AGENT_CONNECTORS": {"label": "Per-Agent Private Connectors", "role": "user", "category": "Agents & Access", "status": "stable", "note": "Let a connector be private to a user (owner_user_id) or bound to a single agent/studio (studio_id), instead of org-wide. NULL/NULL = org-wide (unchanged)."},
    "HYBRID_GROUP_ACCESS": {"label": "Group-Based Agent Access", "role": "user", "category": "Agents & Access", "status": "stable", "note": "Share an agent/studio to a GROUP (incl. AD/LDAP-synced groups) — every group member gets access and the agent auto-appears in their studios list + chat dropdown. Reuses ResourceGrant (resource_type='studio', principal_type='group'). Default OFF."},
    "HYBRID_FILE_BROWSER": {"label": "File Browser (SharePoint/OneDrive/Drive)", "role": "user", "category": "Agents & Access", "status": "stable", "note": "Browse a SharePoint/OneDrive/Google Drive connector's folders/files with YOUR own Microsoft/Google sign-in (each user sees only what their identity can read), and ingest picked files as queryable Data Agents."},
    "HYBRID_AGENT_CHANNELS": {"label": "Agent Channels", "role": "user", "category": "Agents & Access", "status": "beta", "note": "Per-agent channels (Slack/Teams/WhatsApp/AI Mailbox/MCP/Telegram) scoped to that agent's pinned data. Config in Studio → Access & Channels. Inbound routing for Slack/Teams/WhatsApp is phase 2 (Telegram routing live)."},
    "HYBRID_AGENT_REPORTS": {"label": "Scheduled Reports (per-agent)", "role": "user", "category": "Agents & Access", "status": "beta", "note": "Per-agent 'Reports' tab: schedule a prompt/dashboard to run on a cadence and email the result to subscribers, sent from the agent's own SMTP identity. UI only; gates the Studio → Reports tab."},
    "HYBRID_RICH_REPORT_EMAIL": {"label": "Rich Report Emails", "role": "agent", "category": "Agents & Access", "status": "beta", "note": "Render scheduled/automated report emails from structured results (clean table + sanitized insights + dashboard image/PDF) instead of dumping the raw agent chat. OFF = legacy raw-content email."},
    "HYBRID_ONECLICK_ARTIFACTS": {"label": "One-click Dashboard / Slides / Excel", "role": "user", "category": "Agents & Access", "status": "beta", "note": "On a report's right panel, turns the empty Dashboard/Slides/Excel states into one-click builders: 'Generate dashboard' (real page artifact), 'Generate slide deck' (python-pptx deck + previews + .pptx) from the report's existing charts, and an auto-filled Excel workbook. Reuses the chat create_artifact pipeline."},
    "HYBRID_AUTO_ARTIFACT": {"label": "Auto-build Dashboard from chat", "role": "user", "category": "Agents & Access", "status": "experimental", "note": "When a chat turn produces a dataset (the agent ran create_data → ≥1 chart) but makes NO artifact, automatically build a dashboard (page artifact) in the background so the Outputs panel isn't empty. Reuses the one-click create_artifact pipeline. Idempotent (only when the report has zero artifacts) + fully fail-soft. Default OFF."},
    "HYBRID_CROSS_SOURCE_UNIFY": {"label": "Cross-Source Unify", "role": "agent", "category": "Intelligence", "status": "experimental", "note": "At ingest, detect same-shape sibling tables (e.g. 6 monthly files with identical columns) and register a unified UNION ALL view (+ a _period column) so the agent queries across them in one shot. Records a union group + emits an instruction. Fail-soft, no migration. Default OFF."},
    "HYBRID_DATA_QUALITY": {"label": "Data Quality Scan", "role": "user", "category": "Intelligence", "status": "experimental", "note": "At ingest, scan columns for quality issues (high null %, type-coercion risk, outliers, near-constant) and emit a data_quality guardrail instruction the agent reads. Pure pandas, fail-soft, no migration. Default OFF."},
    "HYBRID_VALUE_NORMALIZE": {"label": "Value Normalization (canonical)", "role": "agent", "category": "Intelligence", "status": "experimental", "note": "Resolve a canonical value for near-duplicate labels (e.g. 'daily_used__l' vs 'daily_used__l_') and record a value→canonical map so GROUP BY doesn't scatter one category across spellings. Detection only, no data rewrite. Default OFF."},
    "HYBRID_QUOTAS": {"label": "Per-Org Quotas", "role": "agent", "category": "Agents & Access", "status": "stable"},
    "HYBRID_DOMAIN_PACKS": {"label": "Domain Packs (Skills)", "role": "agent", "category": "Agents & Access", "status": "stable"},
    "HYBRID_PACK_ROUTER": {"label": "Pack Router", "role": "agent", "category": "Agents & Access", "status": "stable"},
    "HYBRID_PACK_AUTOBIND": {"label": "Pack Auto-bind", "role": "review", "category": "Agents & Access", "status": "experimental", "note": "Adds pending rows to review on every train."},
    "HYBRID_TEACH_BOX": {"label": "Teach Box (paste→skill)", "role": "review", "category": "Agents & Access", "status": "stable"},

    # --- Ingest / Autotrain ----------------------------------------------
    "HYBRID_AUTOTRAIN": {"label": "Autotrain (file→pending knowledge)", "role": "review", "category": "Ingest", "status": "stable"},
    "HYBRID_AUTOTRAIN_QA": {"label": "Autotrain — Verified Q&A", "role": "review", "category": "Ingest", "status": "stable"},
    "HYBRID_AUTOTRAIN_PROFILE": {"label": "Autotrain — Profile", "role": "agent", "category": "Ingest", "status": "stable"},
    "HYBRID_AUTOTRAIN_ON_INDEX": {"label": "Autotrain on Connector Index", "role": "agent", "category": "Ingest", "status": "experimental", "note": "Auto-trains every new table — costly on big warehouses."},
    "HYBRID_AUTO_QUERIES": {"label": "Auto Example Queries", "role": "review", "category": "Ingest", "status": "stable"},
    "HYBRID_AUTO_EVALS": {"label": "Auto Eval Cases", "role": "review", "category": "Ingest", "status": "stable"},
    "HYBRID_MERGE_SAME_SCHEMA": {"label": "Merge Same-Schema Uploads", "role": "user", "category": "Ingest", "status": "stable"},
    "HYBRID_SMART_HEADER": {"label": "Smart Header + Glossary", "role": "user", "category": "Ingest", "status": "stable"},

    # --- Learning / Brain -------------------------------------------------
    "HYBRID_BRAIN_READ": {"label": "Brain Read (inject memories)", "role": "agent", "category": "Learning", "status": "stable"},
    "HYBRID_DISTILLER": {"label": "Self-Distiller (👎→pending)", "role": "review", "category": "Learning", "status": "stable"},
    "HYBRID_MEMORY_LOOP": {"label": "Memory Loop (👍→pending)", "role": "review", "category": "Learning", "status": "stable"},
    "HYBRID_QUERY_CACHE": {"label": "Reasoning Cache (proven SQL)", "role": "agent", "category": "Learning", "status": "stable"},
    "HYBRID_QUERY_LEARNING": {"label": "Live Query Learning", "role": "review", "category": "Learning", "status": "stable"},
    "HYBRID_RESULT_CACHE": {"label": "Result Cache", "role": "agent", "category": "Learning", "status": "stable", "note": "Uses Redis."},
    "HYBRID_PARQUET_RESULTS": {"label": "Parquet Result Storage", "role": "agent", "category": "Advanced", "status": "stable", "note": "ON by default. Large step results stored as compressed Parquet on disk instead of inline JSON; smaller DB, faster dashboards. Threshold: HYBRID_PARQUET_MIN_ROWS (default 2000)."},
    "HYBRID_ANSWER_CACHE": {"label": "Answer Cache (Tier-0)", "role": "agent", "category": "Learning", "status": "stable", "note": "Uses Redis."},
    "HYBRID_CODE_BANK": {"label": "Code Bank (proven snippets)", "role": "agent", "category": "Learning", "status": "stable"},
    "HYBRID_AGENT_MEMORY": {"label": "Agent Memory", "role": "review", "category": "Learning", "status": "stable"},
    "HYBRID_SKILL_AUTOGROW": {"label": "Skill Auto-grow", "role": "review", "category": "Learning", "status": "stable"},
    "HYBRID_EVAL_HARNESS": {"label": "Eval Harness (result goldens)", "role": "user", "category": "Learning", "status": "stable"},
    "HYBRID_BITEMPORAL": {"label": "Bi-temporal Facts", "role": "user", "category": "Learning", "status": "experimental", "note": "Changes how facts read (time-filtered)."},

    # --- Advanced ---------------------------------------------------------
    "HYBRID_SUBAGENTS": {"label": "Subagent Fan-out", "role": "agent", "category": "Advanced", "status": "experimental", "note": "N× token cost — budget & concurrency capped."},
    "HYBRID_RECURSIVE": {"label": "Recursive Verify", "role": "agent", "category": "Advanced", "status": "experimental", "note": "No-op unless Subagents is also on."},
    "HYBRID_WORKFLOWS": {"label": "Workflow Runner", "role": "user", "category": "Advanced", "status": "stable"},
    "HYBRID_SKILLS": {"label": "Skills (sandbox exec)", "role": "agent", "category": "Advanced", "status": "unstable", "note": "Can livelock the agent loop — use Domain Packs instead."},
    "HYBRID_SKILL_OPTIMIZE": {"label": "Skill Optimizer", "role": "user", "category": "Advanced", "status": "experimental"},
    "HYBRID_CONTEXT_COMPACT": {"label": "Context Compaction", "role": "agent", "category": "Advanced", "status": "experimental"},
    "HYBRID_CONTEXT_COMPACT_LLM": {"label": "Context Compaction — LLM", "role": "agent", "category": "Advanced", "status": "experimental", "note": "Allows one LLM summarize per run (extra cost)."},
    "HYBRID_AMBIGUITY_GATE": {"label": "Ambiguity Gate (clarify first)", "role": "user", "category": "Advanced", "status": "experimental"},
    "HYBRID_JOIN_GRAPH": {"label": "Join Graph context", "role": "agent", "category": "Advanced", "status": "stable"},
    "HYBRID_BRAIN_GRAPH": {"label": "Brain Graph (entity/correlation)", "role": "agent", "category": "Advanced", "status": "experimental", "note": "Empty until edges are mined."},
    "HYBRID_FEDERATION": {"label": "DuckDB Federation", "role": "agent", "category": "Advanced", "status": "needs_dep", "note": "Needs S3/MinIO (FEDERATION_S3_*) — no-op without it."},

    # --- Daemons (background; read at boot → toggle needs restart) ---------
    "HYBRID_INSIGHT_DAEMON": {"label": "Insight Daemon", "role": "agent", "category": "Daemons", "status": "daemon", "note": "Applies after a container restart."},
    "HYBRID_SKILL_OPTIMIZE_DAEMON": {"label": "Skill Optimizer Daemon", "role": "agent", "category": "Daemons", "status": "daemon", "note": "Applies after a container restart."},
    "EVAL_SCHEDULE_ENABLED": {"label": "Eval Schedule Daemon", "role": "agent", "category": "Daemons", "status": "daemon", "note": "Applies after a container restart."},
    "JOIN_MINE_ENABLED": {"label": "Join Mining Daemon", "role": "agent", "category": "Daemons", "status": "daemon", "note": "Applies after a container restart."},
    "STUDIO_LEARN_DAEMON_ENABLED": {"label": "Studio Learn Daemon", "role": "agent", "category": "Daemons", "status": "daemon", "note": "Applies after a container restart."},
}

# Flags hidden from the Feature-Flags UI (and rejected by the PUT route). These
# are KNOWN-UNSTABLE features that livelock the agent loop — we don't want anyone
# enabling them from the UI. The flag code still exists and defaults OFF; this
# only removes the toggle. To re-expose after a redesign, drop the name here.
#   - HYBRID_SKILLS    : sandbox skill exec — livelocks; use Domain Packs instead.
#   - HYBRID_SUBAGENTS : subagent fan-out — instability source (livelocks).
#   - HYBRID_RECURSIVE : no-op unless Subagents is on, so hide it with them.
#   - HYBRID_SKILL_AUTOGROW / SKILL_OPTIMIZE / SKILL_OPTIMIZE_DAEMON : the whole
#       skill self-improvement family dead-ends on HYBRID_SKILLS (authoring is
#       hard-gated on it, optimization needs skill rows that can't exist) — retired
#       with the skill subsystem. Use Domain Packs instead.
# NOTE: HYBRID_CONTEXT_COMPACT_LLM is NO LONGER hidden — the LLM-summarize path is
# now implemented (maybe_compress + async wiring in agent_v2), so the toggle works.
HIDDEN_FLAGS: set[str] = {
    "HYBRID_SKILLS",
    "HYBRID_SUBAGENTS",
    "HYBRID_RECURSIVE",
    "HYBRID_SKILL_AUTOGROW",
    "HYBRID_SKILL_OPTIMIZE",
    "HYBRID_SKILL_OPTIMIZE_DAEMON",
}

# Stable, browser-facing order of the UI sections.
FLAG_CATEGORIES: list[str] = [
    "Core", "Knowledge", "Intelligence", "Agents & Access",
    "Ingest", "Learning", "Advanced", "Daemons",
]


async def load_overrides_from_db(db) -> int:
    """Scan organization_settings rows and apply their hybrid overrides.

    Reads each row's `config['hybrid_overrides']` (a dict of
    {ENV_NAME: bool}) and merges every recognised key into `_OVERRIDES`.
    Only keys present in UPGRADE_FLAGS are honoured (ignores stale/unknown
    keys). Returns the number of override keys loaded. Never raises into the
    boot path — on any error it returns whatever was loaded so far.

    NOTE: single-project deploys have one org; if multiple org rows set the
    same key the last-scanned row wins (process-wide store, not per-org).
    """
    loaded = 0
    try:
        from sqlalchemy import select  # local import: keep module dep-free
        from app.models.organization_settings import OrganizationSettings

        result = await db.execute(select(OrganizationSettings))
        rows = result.scalars().all()
        for row in rows:
            config = getattr(row, "config", None) or {}
            overrides = config.get("hybrid_overrides") if isinstance(config, dict) else None
            if not isinstance(overrides, dict):
                continue
            for env_name, value in overrides.items():
                if env_name in UPGRADE_FLAGS and value is not None:
                    _OVERRIDES[env_name] = bool(value)
                    loaded += 1
    except Exception:
        # Never break boot over a malformed override row.
        return loaded
    return loaded


class HybridFlags:
    """Lazily-read flag registry. Read at access so env changes (tests) apply."""

    # --- Per-agent access control + channels ---------------------------------
    @property
    def AGENT_ACL(self) -> bool:
        # Enforce StudioMember / share_scope at chat time (per-agent access)
        # and honour per-agent model override (Studio.config.model_id).
        return _bool("HYBRID_AGENT_ACL", True)

    @property
    def USER_GROUPS(self) -> bool:
        # User-owned contact groups: a normal (non-admin) member can create
        # their OWN groups (owner_user_id set), add org members, and use them
        # as reusable share targets. Org/admin/LDAP groups (owner_user_id NULL)
        # are unaffected. Gates the /api/me/groups* + /api/me/contacts router.
        # Default OFF.
        return _bool("HYBRID_USER_GROUPS", True)

    @property
    def AGENT_CONNECTORS(self) -> bool:
        # Per-agent PRIVATE connectors: a connector can be scoped private to a
        # user (owner_user_id set) or bound to a single agent/studio (studio_id
        # set), instead of org-wide. Org-wide connectors (owner_user_id NULL +
        # studio_id NULL) are unaffected. Default OFF.
        return _bool("HYBRID_AGENT_CONNECTORS", True)

    @property
    def GROUP_ACCESS(self) -> bool:
        # Group-based agent/studio access: share a studio to a GROUP via
        # ResourceGrant(resource_type='studio', principal_type='group'). Every
        # member of the granted group (incl. AD/LDAP-synced groups) resolves to
        # viewer/editor and the studio auto-appears in their list + chat
        # dropdown. Off => no group resolution (owner/member/org only). Default OFF.
        return _bool("HYBRID_GROUP_ACCESS", True)

    @property
    def AGENT_CHANNELS(self) -> bool:
        # Per-agent external channels (Telegram bot bound to one Studio,
        # with member-only audience + verification). Default OFF.
        return _bool("HYBRID_AGENT_CHANNELS", True)

    @property
    def AGENT_REPORTS(self) -> bool:
        # Per-agent "Reports" tab: schedule a prompt/dashboard to run on a
        # cadence and email the result to subscribers from the agent's own SMTP
        # identity. UI-gating only (Studio → Reports tab + scheduled-report
        # CRUD routes). Default OFF.
        return _bool("HYBRID_AGENT_REPORTS", True)

    @property
    def RICH_REPORT_EMAIL(self) -> bool:
        # Render scheduled/automated report emails from STRUCTURED results
        # (clean table + sanitized insights + dashboard image/PDF) via the
        # universal delivery layer, instead of dumping the raw agent chat
        # content. OFF = legacy raw-content email (byte-identical old path).
        # Default OFF.
        return _bool("HYBRID_RICH_REPORT_EMAIL", True)

    @property
    def FILE_BROWSER(self) -> bool:
        # Per-user file browser for the existing SharePoint/OneDrive/Google
        # Drive connectors: navigate folders/files using THIS user's resolved
        # per-user credentials (so the source's own ACLs isolate each user),
        # then ingest picked files as queryable Data Agents. Gates the
        # /api/connections/{id}/files router only; no agent-loop effect.
        # Default OFF.
        return _bool("HYBRID_FILE_BROWSER", True)

    @property
    def ONECLICK_ARTIFACTS(self) -> bool:
        # One-click builders on a report's right panel (Dashboard / Slides /
        # Excel): build a REAL page or slides artifact from the report's existing
        # visualizations (reusing the chat create_artifact pipeline) and
        # auto-fill the Excel workbook — instead of dead "No X yet" empty states.
        # Gates POST /api/reports/{id}/{dashboard,slides}/generate + the FE
        # buttons only; no agent-loop effect. Default OFF.
        return _bool("HYBRID_ONECLICK_ARTIFACTS", True)

    @property
    def AUTO_ARTIFACT(self) -> bool:
        # Auto-build a dashboard (page artifact) in the BACKGROUND after a
        # successful chat turn that produced a dataset (create_data → ≥1
        # visualization/step) but made NO artifact — so the Outputs panel isn't
        # empty. Reuses the one-click create_artifact pipeline
        # (report_slides._generate_artifact, mode='page'). Idempotent (skips when
        # the report already has any artifact) + fail-soft (never affects the
        # chat response). No agent-loop effect. Default OFF.
        return _bool("HYBRID_AUTO_ARTIFACT", True)

    @property
    def CROSS_SOURCE_UNIFY(self) -> bool:
        # At ingest, detect same-shape sibling tables (e.g. 6 monthly files with
        # identical columns) and register a unified logical view (UNION ALL +
        # a _period column) so the agent can query across them in one shot,
        # instead of UNIONing by hand. Records a union group + emits an
        # instruction. Fail-soft, no migration. Default OFF.
        return _bool("HYBRID_CROSS_SOURCE_UNIFY", False)

    @property
    def DATA_QUALITY(self) -> bool:
        # At ingest, scan columns for quality issues (high null %, type-coercion
        # risk, outliers, constant/near-constant) and emit a data_quality
        # guardrail instruction the agent reads. Pure pandas, fail-soft,
        # no migration. Default OFF.
        return _bool("HYBRID_DATA_QUALITY", False)

    @property
    def VALUE_NORMALIZE(self) -> bool:
        # Extend deep-profile variant detection to resolve a CANONICAL value for
        # near-duplicate labels (e.g. 'daily_used__l' vs 'daily_used__l_') and
        # record a value→canonical map so GROUP BY doesn't scatter one real
        # category across spellings. Detection only (no data rewrite). Default OFF.
        return _bool("HYBRID_VALUE_NORMALIZE", False)

    # --- Slice 1: foundation -------------------------------------------------
    @property
    def DUAL_SCHEMA(self) -> bool:
        # Phase 2: DB-level read-only engine + analytics/staging schemas.
        return _bool("HYBRID_DUAL_SCHEMA", True)

    @property
    def ENGINEER_ASSETS(self) -> bool:
        # Phase 3: build_data_asset tool (reusable analytics.* views).
        return _bool("HYBRID_ENGINEER_ASSETS", True)

    # --- Autotrain: dash-style "upload a file -> train -> answer" ------------
    @property
    def AUTOTRAIN(self) -> bool:
        # Ingest a flat file (or connector table) into `staging`, profile it,
        # and auto-propose PENDING knowledge (semantic/metrics/verified-Q&A).
        # Source-agnostic, approval-only, vectorless. Default OFF.
        return _bool("HYBRID_AUTOTRAIN", True)

    @property
    def AUTOTRAIN_QA(self) -> bool:
        # Sub-flag: generate+execute+keep verified Q&A during autotrain.
        return _bool("HYBRID_AUTOTRAIN_QA", True)

    @property
    def AUTOTRAIN_PROFILE(self) -> bool:
        # Sub-flag: write profile_v2 JSONB onto datasource_tables.metadata_json.
        return _bool("HYBRID_AUTOTRAIN_PROFILE", True)

    @property
    def AUTOTRAIN_ON_INDEX(self) -> bool:
        # OPT-IN: after a connector finishes indexing, auto-train its NEW tables
        # into pending knowledge. Default OFF — can be costly on big warehouses.
        return _bool("HYBRID_AUTOTRAIN_ON_INDEX")

    # --- Workflow runner (deterministic conductor + verifier gate) ----------
    @property
    def WORKFLOWS(self) -> bool:
        # Deterministic batch pipeline: fan a work-list through fixed stages, a
        # per-item judge gate (pass/retry/skip), full log. Reuses subagent
        # workers. For reliable bulk ops (train warehouse, eval backfill). Default OFF.
        return _bool("HYBRID_WORKFLOWS", True)

    # --- Skill Optimizer (SkillOpt: skill doc as trainable artifact) ---------
    @property
    def SKILL_OPTIMIZE(self) -> bool:
        # Closed-loop skill optimization: rollout a skill on held-out eval
        # goldens -> Judge score -> LLM textual edits -> accept only if the
        # held-out score strictly improves -> new version, status pending.
        # Approval-gated, OpenRouter-only, no GPU. Default OFF.
        return _bool("HYBRID_SKILL_OPTIMIZE")

    @property
    def SKILL_OPTIMIZE_DAEMON(self) -> bool:
        # Sub-flag: nightly leader-gated auto-optimize of stale/low-scoring
        # skills. Default OFF.
        return _bool("HYBRID_SKILL_OPTIMIZE_DAEMON")

    # --- Context compaction (GCC/OpenDerisk: edit + compress + awareness) ----
    @property
    def CONTEXT_COMPACT(self) -> bool:
        # Between/within turns: drop superseded/low-priority sections to a token
        # budget (EDIT), append a "context: X of Y" awareness line (AWARENESS),
        # and optionally LLM-summarize the dropped text (COMPRESS, sub-flag).
        # Longer/cheaper sessions, fewer "context full" failures. Default OFF.
        return _bool("HYBRID_CONTEXT_COMPACT", True)

    @property
    def CONTEXT_COMPACT_LLM(self) -> bool:
        # Sub-flag: allow ONE LLM summarization of dropped/old text per agent run
        # (COMPRESS). Off -> deterministic head-truncate only (no LLM cost).
        return _bool("HYBRID_CONTEXT_COMPACT_LLM", True)

    # --- Bi-temporal facts (Zep/Graphiti: valid_at/invalid_at/superseded_by) --
    @property
    def BITEMPORAL(self) -> bool:
        # Evolving facts (metrics, semantic, memory) get a timeline instead of
        # being overwritten: reads return only currently-valid rows; supersede on
        # re-approve; optional as-of time-travel. Default OFF (reads unfiltered).
        return _bool("HYBRID_BITEMPORAL", True)

    # --- Skill auto-grow (Voyager: 👍 -> draft skill) ------------------------
    @property
    def SKILL_AUTOGROW(self) -> bool:
        # On a 👍'd answer, auto-author a DRAFT personal skill (reuses
        # distill_skill_from_completion). Owner activates it to go live.
        # Self-learning for PROCEDURES (memory tool = facts). Default OFF.
        return _bool("HYBRID_SKILL_AUTOGROW")

    # --- Subagents (orchestrator-worker fan-out) ----------------------------
    @property
    def SUBAGENTS(self) -> bool:
        # `delegate_subtask` tool + orchestrator fan-out: spawn clean-context
        # research workers (LLM->SQL->client->distill) for multi-source/hard Qs.
        # Default OFF — N× tokens; budget + concurrency capped. Single-analyst
        # path is untouched when off.
        return _bool("HYBRID_SUBAGENTS")

    @property
    def RECURSIVE(self) -> bool:
        # Recursive verify: each subagent finding is graded by a cheap critic;
        # HARD-error findings are re-delegated with the reviewer note (bounded
        # loop, default 2 retries via HYBRID_RECURSIVE_MAX_RETRIES). Rides on
        # the subagent path — no-op unless SUBAGENTS is also on. Default OFF.
        return _bool("HYBRID_RECURSIVE")

    @property
    def AGENT_MEMORY(self) -> bool:
        # `remember`/`recall` tools + a memory context section. Agent stows +
        # pages cross-session state. Personal scope = live; shared = pending.
        # Vectorless (PG-FTS + Jaccard). Default OFF.
        return _bool("HYBRID_AGENT_MEMORY", True)

    @property
    def ANSWER_CACHE(self) -> bool:
        # Tier-0 Redis answer-cache.
        return _bool("HYBRID_ANSWER_CACHE", True)

    @property
    def AMBIGUITY_GATE(self) -> bool:
        # R3 "ask before assuming" gate: pre-planning ambiguity classifier that
        # makes the agent clarify (via the clarify tool) instead of assuming a
        # year/metric/entity. Vectorless, OpenRouter-only, fail-open. Default OFF.
        return _bool("HYBRID_AMBIGUITY_GATE", False)

    @property
    def SCOPE_GATE(self) -> bool:
        # Per-agent SCOPE GUARDRAIL: a zero-LLM directive injected pre-loop that
        # binds the agent to its OWN connected data sources. Off-topic / general-
        # knowledge / current-events questions (e.g. "who is president of usa")
        # are REFUSED — the agent must not answer them even if the model knows,
        # and instead redirects to a data question. Grounded per-Studio by the
        # report's pinned data-source names, so each agent's scope is its own.
        # Fail-open (never blocks a real data question). Default ON — every agent
        # should be guarded.
        return _bool("HYBRID_SCOPE_GATE", True)

    @property
    def DASH_VERSIONS(self) -> bool:
        # Dashboard layout VERSIONING: deliberate semantic changes (add/remove
        # chart from chat, manual remove, autopilot) snapshot a NEW immutable
        # layout version + keep all prior ones (restore-able). In-place
        # drag/resize stays a single-version mutate. Mainly gates FE behavior;
        # the snapshot/restore endpoints still work when off. Default ON.
        return _bool("HYBRID_DASH_VERSIONS", True)

    # --- Slice 2: brain + skills --------------------------------------------
    @property
    def BRAIN_READ(self) -> bool:
        # Phase 4: inject brain memories + cached queries into context.
        return _bool("HYBRID_BRAIN_READ", True)

    @property
    def DISTILLER(self) -> bool:
        # Phase 5: 👎 self-distill -> pending memory.
        return _bool("HYBRID_DISTILLER", True)

    @property
    def QUERY_CACHE(self) -> bool:
        # Phase 5: reasoning-cache (param-swap proven SQL).
        return _bool("HYBRID_QUERY_CACHE", True)

    @property
    def SKILLS(self) -> bool:
        # Phase 6: self-service skills subsystem.
        return _bool("HYBRID_SKILLS")

    @property
    def STUDIOS(self) -> bool:
        # Studios: NotebookLM-style shareable agent containers. Default OFF.
        return _bool("HYBRID_STUDIOS", True)

    # --- Slice 3: federation + correlation ----------------------------------
    @property
    def FEDERATION(self) -> bool:
        # Phase 7: DuckDB cross-source federation.
        return _bool("HYBRID_FEDERATION", True)

    @property
    def BRAIN_GRAPH(self) -> bool:
        # Phase 8: Apache AGE entity/correlation graph. Default OFF.
        return _bool("HYBRID_BRAIN_GRAPH", True)

    @property
    def INSIGHT_DAEMON(self) -> bool:
        # Phase 8: proactive insight daemon (leader-gated). Default OFF.
        return _bool("HYBRID_INSIGHT_DAEMON", True)

    @property
    def JOIN_GRAPH(self) -> bool:
        # Phase 6: join-graph context (relationship/join edges injected into
        # the planner, mined offline). Default OFF.
        return _bool("HYBRID_JOIN_GRAPH", True)

    @property
    def JOIN_MINE_ENABLED(self) -> bool:
        # Phase 6: nightly join-mining daemon (leader-gated). NOTE: no HYBRID_
        # prefix — matches EVAL_SCHEDULE_ENABLED naming convention. Default OFF.
        return _bool("JOIN_MINE_ENABLED", True)

    @property
    def STUDIO_LEARN_DAEMON(self) -> bool:
        # Org master switch for the per-studio self-learn daemon. Reads the
        # override layer (DB toggle / env), so the Feature-Flags UI toggle works
        # without a compose env var. Per-studio cadence is stored on the studio.
        return _bool("STUDIO_LEARN_DAEMON_ENABLED", True)

    # --- Slice 4: scale harden ----------------------------------------------
    @property
    def QUOTAS(self) -> bool:
        # Phase 9: per-org request/token quota enforcement (UsagePolicy). Default OFF.
        return _bool("HYBRID_QUOTAS", True)

    # --- Slice 5: knowledge layer -------------------------------------------
    @property
    def SEMANTIC_LAYER(self) -> bool:
        # dash semantic model: per-table/column meaning injected into context.
        return _bool("HYBRID_SEMANTIC_LAYER", True)

    @property
    def METRICS_CATALOG(self) -> bool:
        # dash metrics catalog: named metric -> SQL definition.
        return _bool("HYBRID_METRICS_CATALOG", True)

    @property
    def GOVERNANCE(self) -> bool:
        # Kepler Phase 1: owner / freshness / PII metadata on semantic tables,
        # injected as a per-table governance footer + planner PII rule. Default OFF.
        return _bool("HYBRID_GOVERNANCE", True)

    @property
    def AUTOMAP(self) -> bool:
        # Feature 1: auto-configure-from-doc. Extract column descriptions +
        # instructions + examples from an uploaded definitions xlsx / deck pptx
        # and apply them (descriptions live, instructions/examples pending). Default OFF.
        return _bool("HYBRID_AUTOMAP", True)

    @property
    def COMPLIANCE_GATE(self) -> bool:
        # Feature 4: on-demand, advisory, read-only compliance & data-integrity
        # scan endpoint (dedup + required-field quality). Default OFF.
        return _bool("HYBRID_COMPLIANCE_GATE", True)

    @property
    def COLUMN_INTEL(self) -> bool:
        # Batch B: pre-train per-column profiler (role + allowed values +
        # distinct + null_pct) merged into DataSourceTable.columns[].metadata,
        # surfaced into the schema XML so the agent knows each column up front.
        # Default OFF.
        return _bool("HYBRID_COLUMN_INTEL", True)

    @property
    def AUTO_QUERIES(self) -> bool:
        # Auto-train pipeline: LLM generates example SQL per pinned source,
        # runs read-only, saves verified queries to the library. Default OFF.
        return _bool("HYBRID_AUTO_QUERIES", True)

    @property
    def AUTO_EVALS(self) -> bool:
        # Auto-train pipeline: LLM generates golden eval cases from real data
        # aggregates (grounded expectations). Creation only. Default OFF.
        return _bool("HYBRID_AUTO_EVALS", True)

    @property
    def FOLLOWUPS(self) -> bool:
        # Suggested follow-up questions after each chat answer (ChatGPT/Claude
        # style). Generated per-agent: grounded in the Studio's voice + active
        # instructions + real column values, so each agent suggests its own
        # follow-ups. Default OFF.
        return _bool("HYBRID_FOLLOWUPS", True)

    @property
    def CODE_BANK(self) -> bool:
        # Kepler Phase 2: capture proven generate_df python on success + inject the
        # closest snippet(s) as PROVEN APPROACHES context (never executed). Default OFF.
        return _bool("HYBRID_CODE_BANK", True)

    @property
    def MEMORY_LOOP(self) -> bool:
        # Kepler Phase 3: on 👍, draft pending knowledge (proven SQL -> QueryLibraryItem,
        # bless captured code) with chat provenance. Approval-gated. Default OFF.
        return _bool("HYBRID_MEMORY_LOOP", True)

    @property
    def EVAL_HARNESS(self) -> bool:
        # Phase 4 (eval result-set goldens): result_set matcher + save-as-golden /
        # context-change re-run hooks + FE harness UI. Default OFF.
        return _bool("HYBRID_EVAL_HARNESS", True)

    @property
    def EVAL_SCHEDULE_ENABLED(self) -> bool:
        # Phase 4: nightly scheduled re-run of result-set goldens (leader-gated
        # daemon). NOTE: no HYBRID_ prefix — matches PLAN_KEPLER.md naming. Default OFF.
        return _bool("EVAL_SCHEDULE_ENABLED", True)

    # --- Domain Packs (lightweight "skills" engine — not native Skills) ------
    @property
    def DOMAIN_PACKS(self) -> bool:
        # Master flag for the Domain Packs subsystem: declarative method files
        # (app/ai/packs/library) bound per-agent to real columns and injected
        # into the planner as a method+binding block. Rides the default
        # create_data/create_artifact loop — NO sandbox exec (unlike native
        # HYBRID_SKILLS, which livelocks). When OFF nothing reads the
        # studio_bound_packs table and the agent loop is byte-identical. Default OFF.
        return _bool("HYBRID_DOMAIN_PACKS", True)

    @property
    def PACK_AUTOBIND(self) -> bool:
        # Sub-flag: during studio train, auto-try binding every library pack to
        # the agent's profiled columns and write PENDING studio_bound_packs rows
        # (review-gated before active). Off -> packs only bind on explicit
        # request. No-op unless DOMAIN_PACKS is also on. Default OFF.
        return _bool("HYBRID_PACK_AUTOBIND", True)

    @property
    def PACK_ROUTER(self) -> bool:
        # Sub-flag: at query time, candidate-gate ACTIVE bound packs, score vs
        # the question, and inject the top-1 method+binding into the planner.
        # Off -> packs are bound/visible but never auto-injected. No-op unless
        # DOMAIN_PACKS is also on. Default OFF.
        return _bool("HYBRID_PACK_ROUTER", True)

    @property
    def TEACH_BOX(self) -> bool:
        # Teach Box: paste an existing analysis / SOP, one LLM call classifies it
        # into SKILL | INSTRUCTION | KNOWLEDGE | DATA-RULE spans, each routed to
        # its surface (SKILL -> user-authored domain pack bound to the studio;
        # INSTRUCTION/DATA-RULE -> StudioInstruction; KNOWLEDGE -> KnowledgeDoc).
        # Everything is born pending behind the existing review gate. Gates only
        # the /studios/{id}/teach endpoints; no agent-loop effect. Default OFF.
        return _bool("HYBRID_TEACH_BOX", True)

    @property
    def MERGE_SAME_SCHEMA(self) -> bool:
        # Ingest Task 5: same-schema spreadsheet uploads collapse into ONE
        # data source + table instead of N sources. (a) Content-hash dedup —
        # a byte-identical re-upload returns the existing source. (b) Same-schema
        # append — when the new file's normalized column-set matches an existing
        # spreadsheet source in the same org, the new file's path is added to
        # that source's connection (config['merged_paths']) and the rows are
        # UNION-loaded into the one table with a `_source_label` provenance
        # column, rather than creating a new source+table. Fail-soft: any error
        # falls back to today's one-source-per-file behavior. Default OFF.
        return _bool("HYBRID_MERGE_SAME_SCHEMA", True)

    @property
    def SMART_HEADER(self) -> bool:
        # Ingest Task 6: smarter xlsx ingest. (a) Header detection — if reading a
        # sheet with the default header yields a high fraction of `Unnamed: N`
        # columns, scan the first rows for the real header row and re-read. (b)
        # Glossary routing — a field-definition / data-dictionary sheet (2-3
        # cols of name->description, or filename/sheet name contains
        # defin/glossary/dictionary) is routed into the Knowledge layer
        # (KnowledgeDoc, pending) so its terms can map onto OTHER sources'
        # columns, instead of landing as a junk `Unnamed` queryable table.
        # Conservative — only reroutes when confident. Default OFF.
        return _bool("HYBRID_SMART_HEADER", True)

    @property
    def RESULT_CACHE(self) -> bool:
        # Task 7: deterministic result cache. Keyed by (normalized question text +
        # the report's per-source row-count watermark signature). On a HIT with an
        # unchanged watermark, serve the stored create_data result and SKIP codegen
        # + execution entirely. A re-train / new upload bumps the watermark -> the
        # key changes -> natural miss -> rebuild once. Never serves a stale entry
        # when the watermark differs. Default OFF.
        return _bool("HYBRID_RESULT_CACHE", True)

    @property
    def PARQUET_RESULTS(self) -> bool:
        # Store large step result sets as compressed Parquet files on disk instead
        # of inline JSON in Postgres. Shrinks the DB + speeds dashboard loads; rows
        # are hydrated transparently on read. Small results stay inline. Default ON.
        return _bool("HYBRID_PARQUET_RESULTS", True)

    @property
    def PARQUET_MIN_ROWS(self) -> int:
        # Row-count threshold: results with >= this many rows go to Parquet; smaller
        # results stay inline JSON (Parquet's footer overhead isn't worth it). Env knob.
        return _int("HYBRID_PARQUET_MIN_ROWS", 2000)

    @property
    def QUERY_LEARNING(self) -> bool:
        # Task 8: live query-learning. When a create_data step SUCCEEDS, persist its
        # working SQL/approach to the query library tagged with the question (review-
        # gated, born pending), marked a win, so future similar questions can reuse
        # it. A fail-then-retry-success records the corrected approach as positive
        # (and optionally the dead path as a down-weighted negative studio note).
        # Reuse is injected into the planner context the same way auto-queries are.
        # Default OFF.
        return _bool("HYBRID_QUERY_LEARNING", True)

    @property
    def DOC_KNOWLEDGE(self) -> bool:
        # Kepler Phase 5: company-docs RAG. Approved docs are chunked + PG
        # full-text-searched (VECTORLESS — no embedder in image) and the top
        # matches injected as a "### Company definitions" block to resolve
        # business-term ambiguity. Approval-gated. Default OFF.
        return _bool("HYBRID_DOC_KNOWLEDGE", True)

    @property
    def PROFILE_V2(self) -> bool:
        # Wave1 P1: deep profiler — per-column role (DIMENSION/STATE/MEASURE/
        # IDENTIFIER/TEMPORAL) + top-3 values/freq + variant warnings, stored in
        # DataSourceTable.metadata_json['profile_v2'] + injected as a compact
        # 80-char/col prompt catalog. Default OFF.
        return _bool("HYBRID_PROFILE_V2", True)

    @property
    def PROACTIVE_INSIGHTS(self) -> bool:
        # Wave1 P2: z-score/IQR anomaly + trend scan on result df → insights[]
        # attached post-create_data, rendered as chips. Default OFF.
        return _bool("HYBRID_PROACTIVE_INSIGHTS", True)

    @property
    def SENSE_MAKING(self) -> bool:
        # F10: post-answer decision layer — deterministic signals + 1 cheap LLM → sense_making card. OFF.
        return _bool("HYBRID_SENSE_MAKING", True)

    @property
    def AUTO_MODEL(self) -> bool:
        # Auto model selection: a complexity classifier routes each question to the
        # cheapest capable model (FAST/BALANCED/REASON). Sentinel model_id "auto". OFF.
        return _bool("HYBRID_AUTO_MODEL", True)

    @property
    def FORECAST(self) -> bool:
        # Wave1 P3: Prophet forecast tool (df[date,value] → forecast df). OFF.
        return _bool("HYBRID_FORECAST", True)

    @property
    def GOLDEN_QUERIES(self) -> bool:
        # Wave1 P4: promote thumbs-up / repeat-success learned queries to golden;
        # golden ranks first in coder injection. Default OFF.
        return _bool("HYBRID_GOLDEN_QUERIES", True)

    @property
    def VERIFIED_METRICS(self) -> bool:
        # Wave1 P7: executable locked MetricDefinition (run via metric tool,
        # overrides agent formula) + drift check. Default OFF.
        return _bool("HYBRID_VERIFIED_METRICS", True)

    @property
    def SEMANTIC_SEARCH(self) -> bool:
        # Wave1 P8: hybrid pgvector + BM25 RRF search + knowledge graph. OFF.
        return _bool("HYBRID_SEMANTIC_SEARCH", True)

    @property
    def CODE_ENRICH(self) -> bool:
        # Wave1 P6: L3 Codex code-enrich — extract grain + derived-column formulas
        # + population from table/view DDL source SQL, store in
        # DataSourceTable.metadata_json['pipeline_logic'], inject a compact
        # PIPELINE LOGIC prompt block. Meaning lives in code, not schemas. Default OFF.
        return _bool("HYBRID_CODE_ENRICH", True)

    @property
    def AGENT_TEMPLATES(self) -> bool:
        # Share an agent's data-agnostic best practices (rules, metric formulas,
        # example patterns, skills, persona) as a portable, versioned template that
        # others bind to their own columns. Export/Gallery/bind. Default OFF.
        return _bool("HYBRID_AGENT_TEMPLATES", True)

    @property
    def FOLDER_SYNC(self) -> bool:
        # Desktop Folder Sync agent: a local tray app watches a folder and pushes
        # changed Excel/CSV files (API-key authed) to /api/sync/file, which delta-
        # upserts them into a per-agent DataSource. Like Claude Code for data.
        # Default OFF.
        return _bool("HYBRID_FOLDER_SYNC", True)

    def snapshot(self) -> dict[str, bool]:
        """All flags as a dict (for /health, debugging, tests)."""
        return {
            "DUAL_SCHEMA": self.DUAL_SCHEMA,
            "ENGINEER_ASSETS": self.ENGINEER_ASSETS,
            "ANSWER_CACHE": self.ANSWER_CACHE,
            "BRAIN_READ": self.BRAIN_READ,
            "DISTILLER": self.DISTILLER,
            "QUERY_CACHE": self.QUERY_CACHE,
            "SKILLS": self.SKILLS,
            "STUDIOS": self.STUDIOS,
            "FEDERATION": self.FEDERATION,
            "BRAIN_GRAPH": self.BRAIN_GRAPH,
            "INSIGHT_DAEMON": self.INSIGHT_DAEMON,
            "JOIN_GRAPH": self.JOIN_GRAPH,
            "JOIN_MINE_ENABLED": self.JOIN_MINE_ENABLED,
            "STUDIO_LEARN_DAEMON": self.STUDIO_LEARN_DAEMON,
            "QUOTAS": self.QUOTAS,
            "SEMANTIC_LAYER": self.SEMANTIC_LAYER,
            "METRICS_CATALOG": self.METRICS_CATALOG,
            "GOVERNANCE": self.GOVERNANCE,
            "CODE_BANK": self.CODE_BANK,
            "MEMORY_LOOP": self.MEMORY_LOOP,
            "EVAL_HARNESS": self.EVAL_HARNESS,
            "EVAL_SCHEDULE_ENABLED": self.EVAL_SCHEDULE_ENABLED,
            "DOC_KNOWLEDGE": self.DOC_KNOWLEDGE,
            "RESULT_CACHE": self.RESULT_CACHE,
            "PARQUET_RESULTS": self.PARQUET_RESULTS,
            "QUERY_LEARNING": self.QUERY_LEARNING,
            "MERGE_SAME_SCHEMA": self.MERGE_SAME_SCHEMA,
            "SMART_HEADER": self.SMART_HEADER,
            "CONTEXT_COMPACT": self.CONTEXT_COMPACT,
            "SKILL_OPTIMIZE": self.SKILL_OPTIMIZE,
            "SUBAGENTS": self.SUBAGENTS,
            "RECURSIVE": self.RECURSIVE,
            "FOLLOWUPS": self.FOLLOWUPS,
            "SCOPE_GATE": self.SCOPE_GATE,
            "DASH_VERSIONS": self.DASH_VERSIONS,
            "DOMAIN_PACKS": self.DOMAIN_PACKS,
            "PACK_AUTOBIND": self.PACK_AUTOBIND,
            "PACK_ROUTER": self.PACK_ROUTER,
            "TEACH_BOX": self.TEACH_BOX,
            "PROFILE_V2": self.PROFILE_V2,
            "PROACTIVE_INSIGHTS": self.PROACTIVE_INSIGHTS,
            "SENSE_MAKING": self.SENSE_MAKING,
            "AUTO_MODEL": self.AUTO_MODEL,
            "FORECAST": self.FORECAST,
            "GOLDEN_QUERIES": self.GOLDEN_QUERIES,
            "VERIFIED_METRICS": self.VERIFIED_METRICS,
            "SEMANTIC_SEARCH": self.SEMANTIC_SEARCH,
            "CODE_ENRICH": self.CODE_ENRICH,
            "AGENT_TEMPLATES": self.AGENT_TEMPLATES,
            "FOLDER_SYNC": self.FOLDER_SYNC,
            "USER_GROUPS": self.USER_GROUPS,
            "AGENT_CONNECTORS": self.AGENT_CONNECTORS,
            "GROUP_ACCESS": self.GROUP_ACCESS,
            "FILE_BROWSER": self.FILE_BROWSER,
            "AGENT_REPORTS": self.AGENT_REPORTS,
            "RICH_REPORT_EMAIL": self.RICH_REPORT_EMAIL,
            "ONECLICK_ARTIFACTS": self.ONECLICK_ARTIFACTS,
            "AUTO_ARTIFACT": self.AUTO_ARTIFACT,
            "CROSS_SOURCE_UNIFY": self.CROSS_SOURCE_UNIFY,
            "DATA_QUALITY": self.DATA_QUALITY,
            "VALUE_NORMALIZE": self.VALUE_NORMALIZE,
        }


flags = HybridFlags()
