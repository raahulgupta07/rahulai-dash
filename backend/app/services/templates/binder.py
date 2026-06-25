"""Agent Templates — BIND + INSTANTIATE (Phase 3, HYBRID_AGENT_TEMPLATES).

The consumer (User B) side of Agent Templates. Given a published/draft
``AgentTemplate`` + a target data source + a ``column_map``, this module:

  1. AUTO-MATCHES the template's required column *roles* to the target's real
     columns (``auto_match`` over ``profile_v2`` roles + stdlib fuzzy name
     similarity — no embeddings, no new deps).
  2. APPLIES the binding: rewrites the ``{as}`` placeholder tokens in the
     template ``body_md`` to the consumer's real column names (``apply_binding``).
  3. PARSES the bound body into rules / metrics / example sections
     (``extract_sections``).
  4. INSTANTIATES a brand-new Studio seeded with those rules/examples/metrics —
     every seeded item born ``pending`` / ``draft`` (the review gate), skills
     attached as ``pending`` ``StudioBoundPack`` rows, persona/description set
     from the manifest, and the target data source(s) linked
     (``instantiate_template`` / ``run_instantiate``).

THE CONTRACT (must match exporter.py / parser.py):
  - ``manifest['requires_columns']`` = list of ``{role, as}``; ``role`` ∈
    DIMENSION/STATE/MEASURE/IDENTIFIER/TEMPORAL; ``as`` = placeholder name
    (e.g. ``order_date``).
  - Template body carries ``{as}`` placeholder tokens (e.g. ``{order_date}``,
    ``{revenue}``) inside rules/metrics/examples.
  - ``column_map`` = ``{"<as>": "<real_column_name>"}``. Binding = replace each
    ``{as}`` token with the mapped real column.
  - Target columns + roles come from
    ``DataSourceTable.metadata_json['profile_v2']`` = ``{col: {role, ...}}``.

Nothing seeded is ever auto-active. Fail-soft: ``instantiate_template`` is
transactional (rollback on error) and ``preview_bind`` never raises.
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_template import AgentTemplate
from app.models.datasource_table import DataSourceTable
from app.models.metric_definition import MetricDefinition
from app.models.studio import (
    Studio,
    StudioBoundPack,
    StudioDataSource,
    StudioExample,
    StudioInstruction,
)

logger = logging.getLogger(__name__)

# Roles the contract recognises (kept loose — auto_match works on any role).
KNOWN_ROLES = {"DIMENSION", "STATE", "MEASURE", "IDENTIFIER", "TEMPORAL"}

# Minimum name-similarity to accept a fuzzy match when role alone is ambiguous.
_NAME_SIM_FLOOR = 0.45


# ---------------------------------------------------------------------------
# Pure helpers (no DB) — unit-testable, never raise on normal input.
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Lowercase + split on non-alnum into a token set, for fuzzy compares."""
    return " ".join(t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t)


def _token_jaccard(a: str, b: str) -> float:
    ta = set(_norm(a).split())
    tb = set(_norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _name_sim(a: str, b: str) -> float:
    """Blend token-Jaccard with difflib ratio — both stdlib, no deps."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    jac = _token_jaccard(a, b)
    return max(seq, jac)


def auto_match(requires_columns: list[dict], target_profile: dict) -> dict:
    """Propose ``{as: real_column}`` mapping the template's required roles to the
    target's real columns.

    ``requires_columns``: list of ``{role, as}`` (the binding contract).
    ``target_profile``: ``{real_column_name: role}`` (see ``target_profile`` /
    ``_profile_to_role_map``).

    Strategy per required column:
      1. Gather candidate columns whose role == the required role.
      2. If exactly one candidate -> take it.
      3. If several -> pick the best name similarity between ``as`` and column.
      4. If zero candidates with the role -> fall back to best name similarity
         across ALL columns, but only accept it above ``_NAME_SIM_FLOOR``.
      5. Otherwise leave the ``as`` OUT of the map (caller marks ``needs_user``).

    Each real column is consumed at most once (no double-binding), greedily in
    the order ``requires_columns`` is given.

    Returns ``{"column_map": {...}, "needs_user": [<as names with no match>]}``.
    """
    column_map: dict[str, str] = {}
    needs_user: list[str] = []

    if not isinstance(requires_columns, list):
        return {"column_map": {}, "needs_user": []}

    # normalise the profile to {col: ROLE_UPPER}
    prof: dict[str, str] = {}
    if isinstance(target_profile, dict):
        for col, role in target_profile.items():
            if col is None:
                continue
            prof[str(col)] = str(role or "").upper()

    used: set[str] = set()

    for rc in requires_columns:
        if not isinstance(rc, dict):
            continue
        as_name = rc.get("as") or rc.get("placeholder") or rc.get("name")
        if not as_name:
            continue
        as_name = str(as_name)
        role = str(rc.get("role") or "").upper()

        # candidates sharing the role, not already used
        same_role = [c for c, r in prof.items() if r == role and c not in used]

        chosen: Optional[str] = None
        if len(same_role) == 1:
            chosen = same_role[0]
        elif len(same_role) > 1:
            chosen = max(same_role, key=lambda c: _name_sim(as_name, c))
        else:
            # no role match -> best name similarity across all unused columns
            free = [c for c in prof if c not in used]
            if free:
                best = max(free, key=lambda c: _name_sim(as_name, c))
                if _name_sim(as_name, best) >= _NAME_SIM_FLOOR:
                    chosen = best

        if chosen:
            column_map[as_name] = chosen
            used.add(chosen)
        else:
            needs_user.append(as_name)

    return {"column_map": column_map, "needs_user": needs_user}


def _strip_frontmatter(md: str) -> str:
    """If ``md`` opens with a ``---`` frontmatter fence, return the body after the
    second ``---``. Otherwise return ``md`` unchanged. Defensive."""
    if not md:
        return ""
    text = md.lstrip("﻿")  # strip BOM if any
    if text.lstrip().startswith("---"):
        # find the first fence then the closing one
        # split on lines so a literal '---' inside body text isn't mistaken
        lines = text.splitlines()
        # locate first '---'
        first = None
        for i, ln in enumerate(lines):
            if ln.strip() == "---":
                first = i
                break
        if first is not None:
            for j in range(first + 1, len(lines)):
                if lines[j].strip() == "---":
                    return "\n".join(lines[j + 1:]).lstrip("\n")
    return md


def apply_binding(body_md: str, column_map: dict) -> str:
    """Replace ``{as}`` placeholder tokens in the template body with the mapped
    real column names.

    - Operates on the BODY only — if given a full md doc with frontmatter it is
      stripped first (split on the second ``---``).
    - Unmapped placeholders are LEFT INTACT so the review surfaces them.
    - Only whole ``{token}`` placeholders are replaced (word-ish keys), so prose
      braces are untouched.
    """
    body = _strip_frontmatter(body_md or "")
    if not body or not isinstance(column_map, dict) or not column_map:
        return body

    def _repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        val = column_map.get(key)
        return str(val) if val else m.group(0)

    # {token} where token is a placeholder name (letters/digits/_/.)
    return re.sub(r"\{([A-Za-z0-9_.]+)\}", _repl, body)


def _bullets(block: str) -> list[str]:
    """Extract ``-``/``*``/``1.`` bullet lines from a section block."""
    out: list[str] = []
    for ln in (block or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"^(?:[-*]|\d+[.)])\s+(.*)$", s)
        if m:
            txt = m.group(1).strip()
            if txt:
                out.append(txt)
    return out


def _split_sections(body: str) -> dict[str, str]:
    """Split a markdown body into ``{heading_lower: block_text}`` keyed on ``##``
    (and ``###``) headings."""
    sections: dict[str, str] = {}
    cur: Optional[str] = None
    buf: list[str] = []
    for ln in (body or "").splitlines():
        m = re.match(r"^#{2,6}\s+(.*)$", ln)
        if m:
            if cur is not None:
                sections[cur] = "\n".join(buf).strip()
            cur = m.group(1).strip().lower()
            buf = []
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        sections[cur] = "\n".join(buf).strip()
    return sections


def _match_heading(sections: dict[str, str], *needles: str) -> str:
    """Return the block whose heading contains any needle (substring, lower)."""
    for head, block in sections.items():
        for n in needles:
            if n in head:
                return block
    return ""


def extract_sections(body_md: str) -> dict:
    """Parse the bound body's ``## Rules`` / ``## Metrics`` / ``## Example
    patterns`` sections into structured lists. Defensive — missing sections
    yield empty lists.

    Returns::

        {
          "rules":    [str, ...],
          "metrics":  [{"name": str, "formula": str}, ...],
          "examples": [{"question": str, "method": str}, ...],
        }
    """
    body = _strip_frontmatter(body_md or "")
    sections = _split_sections(body)

    rules = _bullets(_match_heading(sections, "rule"))

    metrics: list[dict] = []
    for line in _bullets(_match_heading(sections, "metric")):
        # forms:  "AOV = sum(...)/count(...)"  |  "AOV: sum(...)"  |  "**AOV** — ..."
        name, formula = _split_named(line)
        if name or formula:
            metrics.append({"name": name, "formula": formula})

    examples: list[dict] = []
    ex_block = _match_heading(sections, "example pattern", "example", "question")
    for line in _bullets(ex_block):
        # Examples use a Q — method delimiter; split on dash/arrow ONLY (never on
        # `=`/`:` which legitimately appear inside the SQL method, e.g. `>=`).
        q, method = _split_example(line)
        examples.append({"question": q or line, "method": method})

    return {"rules": rules, "metrics": metrics, "examples": examples}


def _split_named(line: str) -> tuple[str, str]:
    """Split a bullet into (name/left, formula/right) on the first of
    ``=`` / ``:`` / ``—`` / `` - ``. Strips markdown bold. Defensive."""
    s = (line or "").strip()
    # strip leading bold/quotes around the name
    s = re.sub(r"^\*\*(.+?)\*\*\s*", r"\1 ", s)
    s = s.replace("`", "")
    for sep in ("=", ":", "—", "–"):
        if sep in s:
            left, right = s.split(sep, 1)
            return left.strip(" *"), right.strip()
    # " - " mid-line separator
    m = re.match(r"^(.+?)\s+-\s+(.+)$", s)
    if m:
        return m.group(1).strip(" *"), m.group(2).strip()
    return s.strip(" *"), ""


def _split_example(line: str) -> tuple[str, str]:
    """Split an example bullet into (question, method) on the FIRST dash/arrow
    delimiter only — never on ``=``/``:`` (those appear inside the SQL method,
    e.g. ``created_at >= ...``). Defensive."""
    s = (line or "").strip()
    s = re.sub(r"^\*\*(.+?)\*\*\s*", r"\1 ", s).replace("`", "")
    for sep in ("→", "—", "–", "=>", "->"):
        if sep in s:
            left, right = s.split(sep, 1)
            return left.strip(" *"), right.strip()
    m = re.match(r"^(.+?)\s+-\s+(.+)$", s)
    if m:
        return m.group(1).strip(" *"), m.group(2).strip()
    return s.strip(" *"), ""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def _profile_to_role_map(prof: Any) -> dict[str, str]:
    """``profile_v2`` ({col: {role, ...}}) -> {col: ROLE}. Defensive."""
    out: dict[str, str] = {}
    if not isinstance(prof, dict):
        return out
    for col, info in prof.items():
        if col is None:
            continue
        role = ""
        if isinstance(info, dict):
            role = str(info.get("role") or "")
        out[str(col)] = role.upper()
    return out


async def target_profile(db: AsyncSession, data_source_id: str) -> dict:
    """Merge ``profile_v2`` roles across a data source's ACTIVE
    ``DataSourceTable`` rows into a single ``{col: role}`` map.

    Later tables win on a column-name collision (acceptable — roles agree in
    practice). Never raises; returns ``{}`` on any error / no profile.
    """
    merged: dict[str, str] = {}
    if not data_source_id:
        return merged
    try:
        res = await db.execute(
            select(DataSourceTable).where(
                DataSourceTable.datasource_id == data_source_id,
                DataSourceTable.is_active.is_(True),
            )
        )
        for tb in res.scalars().all():
            meta = tb.metadata_json or {}
            prof = meta.get("profile_v2") if isinstance(meta, dict) else None
            for col, role in _profile_to_role_map(prof).items():
                # don't clobber a known role with an empty one
                if col in merged and merged[col] and not role:
                    continue
                merged[col] = role
    except Exception as e:  # noqa: BLE001
        logger.warning("templates.binder: target_profile failed for ds=%s: %s",
                       data_source_id, e)
    return merged


def _manifest(template: AgentTemplate) -> dict:
    m = getattr(template, "manifest", None)
    return m if isinstance(m, dict) else {}


# ---------------------------------------------------------------------------
# INSTANTIATE
# ---------------------------------------------------------------------------
async def instantiate_template(
    db: AsyncSession,
    *,
    template: AgentTemplate,
    target_data_source_ids: list[str],
    column_map: dict,
    new_name: str,
    owner_user,
    organization,
) -> Optional[Studio]:
    """Create a NEW Studio seeded from ``template`` bound to ``column_map``.

    Seeds (ALL born pending/draft — the review gate, never auto-active):
      - ``Studio`` (persona + description from the manifest)
      - ``StudioDataSource`` for each id in ``target_data_source_ids``
      - ``StudioInstruction`` (status='pending', source='manual') per ``## Rules`` bullet
      - ``StudioExample`` (status='pending', source='manual') per example pattern
      - ``MetricDefinition`` (status='draft', is_locked=False) per ``## Metrics`` bullet
      - ``StudioBoundPack`` (status='pending', source='pack') per manifest skill slug

    Transactional: on any error the txn is rolled back and the error re-raised
    as a soft ``RuntimeError`` (the caller route can map it to an AppError).
    Returns the created ``Studio`` (committed) or raises.
    """
    org_id = getattr(organization, "id", None) or organization
    owner_id = getattr(owner_user, "id", None) or owner_user

    manifest = _manifest(template)
    column_map = column_map if isinstance(column_map, dict) else {}

    # bind body -> rewrite placeholders to real columns, then parse sections
    bound_body = apply_binding(getattr(template, "body_md", "") or "", column_map)
    parsed = extract_sections(bound_body)

    persona = (
        manifest.get("persona")
        or manifest.get("voice")
        or getattr(template, "description", None)
        or None
    )
    description = (
        manifest.get("summary")
        or getattr(template, "description", None)
        or f"Created from template '{getattr(template, 'name', '')}' "
           f"v{getattr(template, 'version', '')}".strip()
    )

    try:
        studio = Studio(
            name=(new_name or getattr(template, "name", "New Agent")),
            description=description,
            persona=persona,
            owner_user_id=owner_id,
            organization_id=org_id,
            share_scope="private",
            config={
                "from_template": {
                    "template_id": getattr(template, "id", None),
                    "slug": getattr(template, "slug", None),
                    "version": getattr(template, "version", None),
                    "column_map": column_map,
                },
            },
        )
        db.add(studio)
        await db.flush()  # need studio.id for children
        studio_id = studio.id

        # link target data sources
        for ds_id in (target_data_source_ids or []):
            if not ds_id:
                continue
            db.add(StudioDataSource(studio_id=studio_id, agent_id=str(ds_id)))

        # primary DS for metric definitions (metrics need a data_source_id)
        primary_ds = None
        for ds_id in (target_data_source_ids or []):
            if ds_id:
                primary_ds = str(ds_id)
                break

        # rules -> pending instructions
        for rule in parsed.get("rules", []):
            if rule:
                db.add(StudioInstruction(
                    studio_id=studio_id,
                    content=rule,
                    source="manual",
                    status="pending",
                ))

        # examples -> pending examples
        for ex in parsed.get("examples", []):
            q = (ex.get("question") or "").strip()
            if not q:
                continue
            method = (ex.get("method") or "").strip()
            db.add(StudioExample(
                studio_id=studio_id,
                question=q,
                # answer is NOT-NULL on the model; method (or a placeholder) fills it
                answer=method or "(method pattern — see SQL)",
                sql=method or None,
                source="manual",
                status="pending",
            ))

        # metrics -> draft MetricDefinition (NOT locked) — one DS required
        if primary_ds:
            for mt in parsed.get("metrics", []):
                name = (mt.get("name") or "").strip()
                formula = (mt.get("formula") or "").strip()
                if not name:
                    continue
                db.add(MetricDefinition(
                    organization_id=org_id,
                    data_source_id=primary_ds,
                    name=name,
                    definition=formula,
                    table_ref="",
                    sql_calc=formula,
                    status="draft",
                    is_locked=False,
                ))

        # skills -> pending StudioBoundPack rows (let the pack bind-gate/train promote)
        uses_skills = manifest.get("uses_skills") or []
        if isinstance(uses_skills, (list, tuple)):
            for slug in uses_skills:
                if not slug:
                    continue
                db.add(StudioBoundPack(
                    studio_id=studio_id,
                    pack_id=str(slug),
                    binding_map=column_map,
                    status="pending",
                    source="pack",
                ))

        await db.commit()
        await db.refresh(studio)
        logger.info(
            "templates.binder: instantiated studio=%s from template=%s "
            "(rules=%d examples=%d metrics=%d skills=%d)",
            studio_id, getattr(template, "id", None),
            len(parsed.get("rules", [])), len(parsed.get("examples", [])),
            len(parsed.get("metrics", [])) if primary_ds else 0,
            len(uses_skills) if isinstance(uses_skills, (list, tuple)) else 0,
        )
        return studio
    except Exception as e:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.error("templates.binder: instantiate failed for template=%s: %s",
                     getattr(template, "id", None), e, exc_info=True)
        raise RuntimeError(f"template_instantiate_failed: {e}") from e


# ---------------------------------------------------------------------------
# Thin, route-wireable entry points (parent route calls these)
# ---------------------------------------------------------------------------
async def _load_template(db: AsyncSession, template_id: str) -> Optional[AgentTemplate]:
    if not template_id:
        return None
    res = await db.execute(
        select(AgentTemplate).where(AgentTemplate.id == template_id)
    )
    return res.scalars().first()


async def run_instantiate(
    db: AsyncSession,
    *,
    template_id: str,
    data_source_ids: list[str],
    column_map: dict,
    name: str,
    owner_user,
    organization,
) -> Studio:
    """Load the ``AgentTemplate`` by id and instantiate a Studio from it.

    The parent's ``POST /api/templates/{id}/instantiate`` route wires straight
    to this. Raises ``RuntimeError`` (soft) if the template is missing or the
    instantiate fails (txn rolled back inside ``instantiate_template``).
    """
    template = await _load_template(db, template_id)
    if template is None:
        raise RuntimeError(f"template_not_found: {template_id}")
    studio = await instantiate_template(
        db,
        template=template,
        target_data_source_ids=list(data_source_ids or []),
        column_map=column_map or {},
        new_name=name,
        owner_user=owner_user,
        organization=organization,
    )
    if studio is None:
        raise RuntimeError("template_instantiate_failed")
    return studio


async def preview_bind(
    db: AsyncSession,
    *,
    template_id: str,
    data_source_id: str,
    organization,
) -> dict:
    """Prefill the wizard's step-2 column mapping.

    Loads the template, reads the target DS's merged ``profile_v2`` role map,
    and runs ``auto_match`` to propose a ``column_map``. Never raises — degrades
    to empties so the wizard can still ask the user.

    Returns ``{column_map, needs_user, requires_columns}``.
    """
    try:
        template = await _load_template(db, template_id)
        if template is None:
            return {"column_map": {}, "needs_user": [], "requires_columns": []}
        manifest = _manifest(template)
        requires = manifest.get("requires_columns") or []
        if not isinstance(requires, list):
            requires = []
        prof = await target_profile(db, data_source_id)
        matched = auto_match(requires, prof)
        return {
            "column_map": matched.get("column_map", {}),
            "needs_user": matched.get("needs_user", []),
            "requires_columns": requires,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("templates.binder: preview_bind failed (tmpl=%s ds=%s): %s",
                       template_id, data_source_id, e)
        return {"column_map": {}, "needs_user": [], "requires_columns": []}


# ---------------------------------------------------------------------------
# Inline self-test (run module directly).
# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    print("apply_binding:",
          apply_binding(
              "AOV = sum({revenue})/count({order_id})",
              {"revenue": "net_sales", "order_id": "inv_id"},
          ))
    print("auto_match:",
          auto_match(
              [
                  {"role": "TEMPORAL", "as": "order_date"},
                  {"role": "MEASURE", "as": "revenue"},
                  {"role": "IDENTIFIER", "as": "order_id"},
                  {"role": "DIMENSION", "as": "region"},
              ],
              {
                  "created_at": "TEMPORAL",
                  "net_sales": "MEASURE",
                  "inv_id": "IDENTIFIER",
                  "customer_country": "DIMENSION",
                  "ship_region": "DIMENSION",
              },
          ))
    print("extract_sections:",
          extract_sections(
              "## Rules\n- Always filter soft-deleted rows\n- Use net amounts\n\n"
              "## Metrics\n- AOV = sum(net_sales)/count(inv_id)\n- GMV: sum(net_sales)\n\n"
              "## Example patterns\n- What was revenue last month? — sum(net_sales) where created_at >= ...\n"
          ))
