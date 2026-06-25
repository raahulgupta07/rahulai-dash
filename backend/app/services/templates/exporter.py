"""Agent Template EXPORTER (Phase 1) — turn a Studio into a portable template.

HYBRID_AGENT_TEMPLATES (default OFF). Additive, never-raise.

Reads a smart Studio's *data-agnostic know-how* — active instructions/rules,
metric definitions (name + sql_calc formula), example *patterns*, bound skill
(pack) refs and persona/voice/summary — strips everything data-specific (rows,
values, credentials, org id, members, literal table/column names) and emits a
versioned markdown template with frontmatter plus a JSON ``manifest`` mirror.

THE TEMPLATE CONTRACT (must match what the binder/gallery agents read)
---------------------------------------------------------------------
Markdown body with YAML-ish frontmatter::

    ---
    name: <studio name>
    version: 1.0.0
    author: <user name or id>
    domain: [<tags>]
    requires_columns:
      - role: TEMPORAL
        as: order_date
      - role: MEASURE
        as: revenue
    uses_skills: [rfm-segmentation, cohort-retention]
    example_questions: ["...", "..."]
    ---
    ## Rules
    - <instruction content, column names -> {placeholder}>
    ## Metrics
    - <metric name> = <sql_calc with columns -> {placeholder}>
    ## Example patterns
    - Q: <question> -> <generalized method / sql with {placeholder}>

``manifest`` (JSON column) == the parsed frontmatter as a dict:
``{name, version, author, domain, requires_columns:[{role,as}],
uses_skills:[...], example_questions:[...]}``.

PLACEHOLDER / requires_columns SCHEME  (deterministic + documented — the binder
and the auto-match wizard rely on THIS exact scheme)
--------------------------------------------------------------------------------
We build a column->placeholder map from ``DataSourceTable.metadata_json
['profile_v2']`` (``{col_name: {role, ...}}``, role in DIMENSION / STATE /
MEASURE / IDENTIFIER / TEMPORAL) across the studio's ACTIVE data-source tables.

The friendly ``as`` name for a placeholder is derived **only from the column's
role** so it carries no data-specific token:

  * the placeholder is the role, lower-cased: ``{temporal}``, ``{measure}`` ...
  * if SEVERAL distinct columns share the same role, the first (alphabetical by
    column name, for determinism) keeps the bare role name and subsequent ones
    are suffixed with a 1-based index: ``{measure}``, ``{measure_2}``,
    ``{measure_3}`` ...
  * if the SAME column name appears in more than one table it maps to one
    placeholder (first role wins, alphabetical by table then column).

``requires_columns`` in the frontmatter/manifest is the set of placeholders we
ACTUALLY emitted (i.e. that appeared in some instruction / metric / example
text after generalization), each as ``{role: <ROLE>, as: <as-name>}``. A
placeholder that never appears in any generalized text is dropped — we only
advertise what the template truly needs.

RAW golden SQL is OFF by default: we never dump ``StudioExample.sql`` verbatim.
With ``include_raw_sql=False`` (default) the "Example patterns" lines describe
the *method* and only show the generalized SQL when a real role->placeholder
substitution happened (so no concrete column survives). Pass
``include_raw_sql=True`` to additionally include the generalized SQL line for
every example that has SQL.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Roles emitted by Deep Profiler v2 (profile_v2). Order = stable iteration.
_KNOWN_ROLES = ("TEMPORAL", "MEASURE", "DIMENSION", "STATE", "IDENTIFIER")


# --------------------------------------------------------------------------- #
# small string helpers
# --------------------------------------------------------------------------- #
def slugify(name: str) -> str:
    """Lower-case, ascii, hyphen-separated stable slug. Never raises."""
    try:
        text = str(name or "").strip()
        if not text:
            return "untitled-template"
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        text = re.sub(r"-{2,}", "-", text)
        return (text or "untitled-template")[:160]
    except Exception:  # pragma: no cover - defensive
        return "untitled-template"


def _bump_patch(version: str) -> str:
    """Bump the PATCH of a semver string (1.0.0 -> 1.0.1). Tolerant of junk."""
    try:
        parts = str(version or "").strip().split(".")
        nums = []
        for i in range(3):
            try:
                nums.append(int(parts[i]))
            except (IndexError, ValueError):
                nums.append(0)
        nums[2] += 1
        return f"{nums[0]}.{nums[1]}.{nums[2]}"
    except Exception:  # pragma: no cover - defensive
        return "1.0.1"


def generalize_text(text: str, colmap: Dict[str, str]) -> str:
    """Replace concrete column names in *text* with ``{placeholder}`` tokens.

    ``colmap`` maps ``column_name -> placeholder`` (e.g. ``{"order_date":
    "{temporal}"}``). Matching is word-boundary based so partial overlaps don't
    bleed (``order`` won't match inside ``order_date``), and we substitute
    LONGEST column names first so ``order_date`` is handled before ``order``.

    Pure / deterministic / never raises — returns the input on any failure.
    """
    if not text or not colmap:
        return text or ""
    try:
        out = str(text)
        # longest names first to avoid partial-overlap clobbering
        for col in sorted(colmap.keys(), key=len, reverse=True):
            if not col:
                continue
            placeholder = colmap[col]
            # word boundary that treats a column name as an identifier token;
            # \b is fine for typical [A-Za-z0-9_] column names.
            pattern = re.compile(r"\b" + re.escape(col) + r"\b")
            out = pattern.sub(placeholder, out)
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("generalize_text failed: %s", e)
        return text or ""


# --------------------------------------------------------------------------- #
# column -> placeholder map (the binding contract source of truth)
# --------------------------------------------------------------------------- #
async def _build_column_placeholder_map(db, *, studio_id: str) -> Dict[str, Dict[str, str]]:
    """Build ``{column_name: {"placeholder": "{as}", "as": as, "role": ROLE}}``.

    Walks the studio's ACTIVE DataSourceTables' ``metadata_json['profile_v2']``
    role catalogs and applies the deterministic scheme documented in the module
    docstring. Never raises — returns ``{}`` on any failure.
    """
    try:
        from sqlalchemy import select
        from app.models.studio import StudioDataSource
        from app.models.datasource_table import DataSourceTable

        # data source ids pinned to this studio
        ds_stmt = select(StudioDataSource.agent_id).where(
            StudioDataSource.studio_id == str(studio_id)
        )
        ds_ids = [r for (r,) in (await db.execute(ds_stmt)).all() if r]
        if not ds_ids:
            return {}

        tbl_stmt = (
            select(DataSourceTable)
            .where(DataSourceTable.datasource_id.in_([str(d) for d in ds_ids]))
            .where(DataSourceTable.is_active.is_(True))
            .order_by(DataSourceTable.name.asc())
        )
        tables = list((await db.execute(tbl_stmt)).scalars().all())

        # collect (column_name -> role), first role wins for a repeated column.
        # iterate tables alphabetically (already ordered) and columns
        # alphabetically for full determinism.
        col_role: Dict[str, str] = {}
        for tbl in tables:
            meta = tbl.metadata_json
            if not isinstance(meta, dict):
                continue
            profile = meta.get("profile_v2")
            if not isinstance(profile, dict) or not profile:
                continue
            for col_name in sorted(profile.keys()):
                info = profile.get(col_name)
                if not isinstance(info, dict):
                    continue
                if col_name in col_role:
                    continue
                role = str(info.get("role") or "DIMENSION").upper()
                if role not in _KNOWN_ROLES:
                    role = "DIMENSION"
                col_role[col_name] = role

        if not col_role:
            return {}

        # assign placeholders per role with index suffixing for collisions.
        # group columns by role, alphabetical within role for stability.
        by_role: Dict[str, List[str]] = {}
        for col_name in sorted(col_role.keys()):
            by_role.setdefault(col_role[col_name], []).append(col_name)

        colmap: Dict[str, Dict[str, str]] = {}
        for role, cols in by_role.items():
            base = role.lower()
            for idx, col_name in enumerate(cols):
                as_name = base if idx == 0 else f"{base}_{idx + 1}"
                colmap[col_name] = {
                    "placeholder": "{" + as_name + "}",
                    "as": as_name,
                    "role": role,
                }
        return colmap
    except Exception as e:
        logger.warning("_build_column_placeholder_map failed for studio %s: %s", studio_id, e)
        return {}


def _flat_colmap(colmap: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """``{column: placeholder}`` view for ``generalize_text``."""
    return {col: meta["placeholder"] for col, meta in colmap.items()}


def _yaml_str_list(items: List[str]) -> str:
    """Render a python list of strings as a JSON-ish inline YAML list."""
    safe = []
    for it in items:
        s = str(it).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
        safe.append(f'"{s}"')
    return "[" + ", ".join(safe) + "]"


def _yaml_bare_list(items: List[str]) -> str:
    """Render a list of identifier-ish tokens as a bare inline YAML list."""
    safe = [str(it).replace("\n", " ").strip() for it in items]
    return "[" + ", ".join(safe) + "]"


# --------------------------------------------------------------------------- #
# main build
# --------------------------------------------------------------------------- #
async def build_template(
    db,
    *,
    studio_id: str,
    author_user: Any,
    organization: Any,
    include_raw_sql: bool = False,
) -> Dict[str, Any]:
    """Build a template dict from a Studio. NEVER raises.

    Returns ``{"name","slug","version","description","domain_tags","body_md",
    "manifest","source_studio_id"}``. On partial failure emits whatever could be
    gathered and logs a warning.
    """
    name = "Untitled Studio"
    description: Optional[str] = None
    persona: Optional[str] = None
    voice: Optional[str] = None
    summary: Optional[str] = None
    domain_tags: List[str] = []

    instructions: List[str] = []
    metrics: List[Tuple[str, str]] = []          # (name, sql_calc)
    examples: List[Tuple[str, Optional[str], Optional[str]]] = []  # (q, answer, sql)
    uses_skills: List[str] = []
    example_questions: List[str] = []

    colmap: Dict[str, Dict[str, str]] = {}

    # author display
    author = ""
    try:
        author = str(getattr(author_user, "name", None) or getattr(author_user, "id", "") or "")
    except Exception:
        author = ""

    # --- 1. Studio core (persona/voice/summary/description) ----------------- #
    try:
        from sqlalchemy import select
        from app.models.studio import Studio

        studio = (
            await db.execute(select(Studio).where(Studio.id == str(studio_id)))
        ).scalars().first()
        if studio is not None:
            name = studio.name or name
            description = studio.description
            persona = studio.persona
            cfg = studio.config if isinstance(studio.config, dict) else {}
            # voice / summary may live in config (defensive — keys vary)
            voice = cfg.get("voice") or cfg.get("tone")
            summary = cfg.get("summary")
            # domain tags may be parked in config
            dt = cfg.get("domain_tags") or cfg.get("domains")
            if isinstance(dt, list):
                domain_tags = [str(x) for x in dt if x]
    except Exception as e:
        logger.warning("build_template: studio core read failed (%s): %s", studio_id, e)

    # voice / summary may instead be a StudioArtifact kind='summary'/'voice'
    try:
        from sqlalchemy import select
        from app.models.studio import StudioArtifact

        arts = list(
            (
                await db.execute(
                    select(StudioArtifact).where(StudioArtifact.studio_id == str(studio_id))
                )
            ).scalars().all()
        )
        for art in arts:
            kind = (art.kind or "").lower()
            if kind == "summary" and not summary:
                summary = art.content
            elif kind == "voice" and not voice:
                voice = art.content
    except Exception as e:
        logger.warning("build_template: artifact read failed (%s): %s", studio_id, e)

    # --- 2. column -> placeholder map --------------------------------------- #
    colmap = await _build_column_placeholder_map(db, studio_id=studio_id)
    flat = _flat_colmap(colmap)

    # --- 3. active instructions --------------------------------------------- #
    try:
        from sqlalchemy import select
        from app.models.studio import StudioInstruction

        rows = list(
            (
                await db.execute(
                    select(StudioInstruction)
                    .where(StudioInstruction.studio_id == str(studio_id))
                    .where(StudioInstruction.status == "active")
                )
            ).scalars().all()
        )
        for r in rows:
            if r.content:
                instructions.append(generalize_text(r.content, flat))
    except Exception as e:
        logger.warning("build_template: instructions read failed (%s): %s", studio_id, e)

    # --- 4. active examples -------------------------------------------------- #
    try:
        from sqlalchemy import select
        from app.models.studio import StudioExample

        rows = list(
            (
                await db.execute(
                    select(StudioExample)
                    .where(StudioExample.studio_id == str(studio_id))
                    .where(StudioExample.status == "active")
                )
            ).scalars().all()
        )
        for r in rows:
            if r.question:
                examples.append((r.question, r.answer, r.sql))
                example_questions.append(generalize_text(r.question, flat))
    except Exception as e:
        logger.warning("build_template: examples read failed (%s): %s", studio_id, e)

    # --- 5. bound skills (packs) -------------------------------------------- #
    try:
        from sqlalchemy import select
        from app.models.studio import StudioBoundPack

        rows = list(
            (
                await db.execute(
                    select(StudioBoundPack.pack_id)
                    .where(StudioBoundPack.studio_id == str(studio_id))
                    .where(StudioBoundPack.status == "active")
                )
            ).all()
        )
        for (pack_id,) in rows:
            if pack_id and pack_id not in uses_skills:
                uses_skills.append(pack_id)
    except Exception as e:
        logger.warning("build_template: bound packs read failed (%s): %s", studio_id, e)

    # --- 6. metric definitions (for the studio's data sources) -------------- #
    try:
        from sqlalchemy import select
        from app.models.studio import StudioDataSource
        from app.models.metric_definition import MetricDefinition

        ds_ids = [
            r
            for (r,) in (
                await db.execute(
                    select(StudioDataSource.agent_id).where(
                        StudioDataSource.studio_id == str(studio_id)
                    )
                )
            ).all()
            if r
        ]
        if ds_ids:
            org_id = str(getattr(organization, "id", "") or "")
            stmt = (
                select(MetricDefinition)
                .where(MetricDefinition.data_source_id.in_([str(d) for d in ds_ids]))
                .where(MetricDefinition.status.in_(("active", "locked")))
            )
            if org_id:
                stmt = stmt.where(MetricDefinition.organization_id == org_id)
            # exclude bi-temporal superseded rows defensively
            stmt = stmt.where(MetricDefinition.invalid_at.is_(None))
            rows = list((await db.execute(stmt)).scalars().all())
            seen = set()
            for m in rows:
                if not m.name or m.name in seen:
                    continue
                seen.add(m.name)
                gen_sql = generalize_text(m.sql_calc or "", flat)
                metrics.append((m.name, gen_sql))
    except Exception as e:
        logger.warning("build_template: metrics read failed (%s): %s", studio_id, e)

    # --- 7. compute requires_columns = placeholders that actually appeared --- #
    # Concatenate all generalized text we emitted, then keep only the
    # placeholders that show up. Order: by role (known order) then index.
    emitted_blob = "\n".join(
        instructions
        + [s for (_, s) in metrics]
        + [generalize_text(q, flat) for (q, _, _) in examples]
        + [generalize_text(sql or "", flat) for (_, _, sql) in examples]
    )
    requires_columns: List[Dict[str, str]] = []
    seen_as = set()
    # stable ordering: role priority then the as-name
    ordered = sorted(
        colmap.values(),
        key=lambda m: (
            _KNOWN_ROLES.index(m["role"]) if m["role"] in _KNOWN_ROLES else 99,
            m["as"],
        ),
    )
    for meta in ordered:
        if meta["placeholder"] in emitted_blob and meta["as"] not in seen_as:
            seen_as.add(meta["as"])
            requires_columns.append({"role": meta["role"], "as": meta["as"]})

    # --- 8. version (bump rule resolved at persist time; default here) ------- #
    version = "1.0.0"
    slug = slugify(name)

    # --- 9. manifest -------------------------------------------------------- #
    manifest: Dict[str, Any] = {
        "name": name,
        "version": version,
        "author": author,
        "domain": domain_tags,
        "requires_columns": requires_columns,
        "uses_skills": uses_skills,
        "example_questions": example_questions,
    }

    # --- 10. body_md -------------------------------------------------------- #
    body_md = _render_body_md(
        name=name,
        version=version,
        author=author,
        domain_tags=domain_tags,
        requires_columns=requires_columns,
        uses_skills=uses_skills,
        example_questions=example_questions,
        persona=persona,
        voice=voice,
        summary=summary,
        instructions=instructions,
        metrics=metrics,
        examples=examples,
        flat_colmap=flat,
        include_raw_sql=include_raw_sql,
    )

    return {
        "name": name,
        "slug": slug,
        "version": version,
        "description": description,
        "domain_tags": domain_tags,
        "body_md": body_md,
        "manifest": manifest,
        "source_studio_id": str(studio_id),
    }


def _render_body_md(
    *,
    name: str,
    version: str,
    author: str,
    domain_tags: List[str],
    requires_columns: List[Dict[str, str]],
    uses_skills: List[str],
    example_questions: List[str],
    persona: Optional[str],
    voice: Optional[str],
    summary: Optional[str],
    instructions: List[str],
    metrics: List[Tuple[str, str]],
    examples: List[Tuple[str, Optional[str], Optional[str]]],
    flat_colmap: Dict[str, str],
    include_raw_sql: bool,
) -> str:
    """Render the markdown body + frontmatter. Never raises."""
    try:
        lines: List[str] = []
        # ---- frontmatter ----
        lines.append("---")
        lines.append(f"name: {name}")
        lines.append(f"version: {version}")
        lines.append(f"author: {author}")
        lines.append(f"domain: {_yaml_bare_list(domain_tags)}")
        lines.append("requires_columns:")
        if requires_columns:
            for rc in requires_columns:
                lines.append(f"  - role: {rc['role']}")
                lines.append(f"    as: {rc['as']}")
        lines.append(f"uses_skills: {_yaml_bare_list(uses_skills)}")
        lines.append(f"example_questions: {_yaml_str_list(example_questions)}")
        lines.append("---")
        lines.append("")

        # ---- optional persona / voice / summary ----
        if persona or voice or summary:
            lines.append("## Persona")
            if persona:
                lines.append(generalize_text(persona, flat_colmap))
            if voice:
                lines.append(f"- Voice: {generalize_text(voice, flat_colmap)}")
            if summary:
                lines.append(f"- Summary: {generalize_text(summary, flat_colmap)}")
            lines.append("")

        # ---- rules ----
        lines.append("## Rules")
        if instructions:
            for ins in instructions:
                lines.append(f"- {ins}")
        else:
            lines.append("- (none)")
        lines.append("")

        # ---- metrics ----
        lines.append("## Metrics")
        if metrics:
            for mname, msql in metrics:
                if msql:
                    lines.append(f"- {mname} = {msql}")
                else:
                    lines.append(f"- {mname}")
        else:
            lines.append("- (none)")
        lines.append("")

        # ---- example patterns ----
        lines.append("## Example patterns")
        if examples:
            for q, answer, sql in examples:
                gq = generalize_text(q, flat_colmap)
                method = None
                if sql:
                    gsql = generalize_text(sql, flat_colmap)
                    if include_raw_sql:
                        method = gsql
                    else:
                        # only show generalized SQL when a real substitution
                        # actually happened (no concrete column survives).
                        if gsql != sql:
                            method = gsql
                if method is None and answer:
                    method = generalize_text(answer, flat_colmap).strip().split("\n")[0][:200]
                if method:
                    lines.append(f"- Q: {gq} -> {method}")
                else:
                    lines.append(f"- Q: {gq}")
        else:
            lines.append("- (none)")
        lines.append("")

        return "\n".join(lines)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("_render_body_md failed: %s", e)
        # minimal valid frontmatter fallback
        return (
            "---\n"
            f"name: {name}\n"
            f"version: {version}\n"
            f"author: {author}\n"
            "domain: []\n"
            "requires_columns:\n"
            "uses_skills: []\n"
            "example_questions: []\n"
            "---\n"
        )


# --------------------------------------------------------------------------- #
# persist
# --------------------------------------------------------------------------- #
async def export_studio_to_template(
    db,
    *,
    studio_id: str,
    author_user: Any,
    organization: Any,
    scope: str = "org",
    include_raw_sql: bool = False,
):
    """Build + persist an AgentTemplate (status='draft'). Returns the ORM row.

    Version bump rule: if a draft/published row with the same slug already
    exists (highest version for that slug), bump its PATCH; else 1.0.0. Failures
    in building never abort — only persistence can raise (caller may catch).
    """
    from app.models.agent_template import AgentTemplate

    payload = await build_template(
        db,
        studio_id=studio_id,
        author_user=author_user,
        organization=organization,
        include_raw_sql=include_raw_sql,
    )

    slug = payload["slug"]
    version = "1.0.0"

    # version bump: find existing rows with this slug, bump highest patch.
    try:
        from sqlalchemy import select
        from app.models.agent_template import AgentTemplate as _AT

        existing = list(
            (
                await db.execute(select(_AT).where(_AT.slug == slug))
            ).scalars().all()
        )
        if existing:
            def _key(v: str):
                parts = (str(v or "0.0.0").split("."))
                out = []
                for i in range(3):
                    try:
                        out.append(int(parts[i]))
                    except (IndexError, ValueError):
                        out.append(0)
                return tuple(out)

            latest = max(existing, key=lambda r: _key(r.version))
            version = _bump_patch(latest.version)
    except Exception as e:
        logger.warning("export_studio_to_template: version-bump lookup failed: %s", e)
        version = "1.0.0"

    # keep manifest version in sync with the resolved row version
    manifest = payload.get("manifest") or {}
    if isinstance(manifest, dict):
        manifest["version"] = version
    body_md = payload.get("body_md") or ""
    # patch the frontmatter version line too (best-effort)
    try:
        body_md = re.sub(r"^version: .*$", f"version: {version}", body_md, count=1, flags=re.M)
    except Exception:
        pass

    scope = scope if scope in ("org", "global") else "org"
    org_id = None
    try:
        org_id = str(getattr(organization, "id", "") or "") or None
    except Exception:
        org_id = None
    author_id = None
    try:
        author_id = str(getattr(author_user, "id", "") or "") or None
    except Exception:
        author_id = None

    row = AgentTemplate(
        name=payload["name"],
        slug=slug,
        version=version,
        description=payload.get("description"),
        domain_tags=payload.get("domain_tags") or [],
        scope=scope,
        status="draft",
        body_md=body_md,
        manifest=manifest,
        author_user_id=author_id,
        organization_id=org_id if scope == "org" else org_id,
        source_studio_id=payload.get("source_studio_id"),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
