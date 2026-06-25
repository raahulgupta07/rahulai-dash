# ROADMAP — CityAgent Analytics (planning index)

Branch `hybrid-brain`. Index of all active plan files + recommended order + status.
Captures the 2026-06-19 planning session. Every workstream is flag-gated
(HARD RULE 4), reuses dash approval gate where it learns (HARD RULE 5), touches
core minimally (HARD RULE 3).

## Plan files
| plan | file | scope | status |
|---|---|---|---|
| Skills like Claude Code | `docs/PLAN_SKILLS.md` | frontmatter, tool-scoping, L3 files, invocation, activation | **S1-S5 DONE**, S6 pending |
| NotebookLM-style Agents | `docs/PLAN_AGENTS.md` | shareable source-grounded agents + members/roles | designed, not started |
| Faster rebuilds | `docs/PLAN_BUILD.md` | base image + BuildKit cache + vendored assets | designed, not started |
| Enterprise connector gating | `docs/PLAN_CONNECTORS_EE.md` | un-badge / un-gate SharePoint/OneDrive/etc | designed, not started |
| Push dashboards to Power BI | `docs/PLAN_POWERBI.md` | build here → push data/report to Power BI | designed, not started |
| Changelog + "What's new" bell | `docs/PLAN_CHANGELOG_WHATSNEW.md` | versioned feature feed + top-nav notification popover | **DONE + BAKED** (v1.2.0) |
| Ingest storage + merge | `docs/PLAN_INGEST_STORAGE.md` | Parquet canonical store + LLM merge-judge for same-schema | designed, not started |
| Installable PWA | `docs/PLAN_PWA.md` | Add-to-Home-Screen / desktop app + Install button + offline shell | **DONE + BAKED** |
| Agent Templates | `docs/PLAN_AGENT_TEMPLATES.md` | export agent know-how → gallery → bind to own data → new agent | **DONE + BAKED** (v1.4.0) |

## Recommended order (rationale)
1. **S6 — ship skills** (`PLAN_SKILLS.md`). 5 phases built, uncommitted/unbaked/
   unverified-live. Cheap to close; bit-rot risk grows. Agents (N5) build on skills
   → prove skills live first.
2. **BUILD — faster rebuilds** (`PLAN_BUILD.md`). Makes every future bake cheap.
   Do before the next heavy feature so iteration is fast. Can fold the S6 bake into
   the first base-image build.
3. **CONNECTORS_EE — un-badge** (`PLAN_CONNECTORS_EE.md`). Tiny backend hot-cp,
   no rebuild. Quick win, do anytime.
4. **AGENTS — NotebookLM agents** (`PLAN_AGENTS.md`). The headline new value.
   Big; do after skills proven + build is fast. N5 wires skills + 2nd-brain per agent.
5. **POWERBI — push dashboards** (`PLAN_POWERBI.md`). New integration; reuses Azure
   OAuth. Tier-1b MVP after the core agent/dashboard story is solid.

## Cross-cutting facts (verified 2026-06-18/19)
- Backend `.py` = hot-iterable (`docker cp` + `py_compile` + `docker restart`); no
  full rebuild. FE `.vue` = needs `nuxt generate` rebuild OR `yarn dev` :3000.
- Single alembic head currently `sk3skillfiles1` (skills migrations unapplied in
  container — apply on next `alembic upgrade`).
- 2nd-brain present + wired (`app/ai/brain/*`): answer-cache, query-learning,
  distiller, brain-graph (pgvector+CTE), serving-funnel. All flag-OFF default.
- Connector badge is API-driven (`requires_license` field from registry →
  FE `isLocked`); enforcement is a SEPARATE list `ENTERPRISE_DATASOURCES` in
  `app/ee/license.py`. `app/ee/` = Dash commercial license — un-gating the paid 4
  (powerbi/qvd/sybase/tableau) is a legal call; un-badging the cosmetic-only ones
  is low risk.
