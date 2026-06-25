# NOTE: parent registers this router in main.py
"""Agent Templates Gallery API — list / detail / publish / import / delete.

Surfaces the shareable Agent Template gallery (HYBRID_AGENT_TEMPLATES, default
OFF). Templates carry a Studio's *data-agnostic* know-how (rules, metric
formulas, example patterns, persona) as a portable, versioned markdown+frontmatter
artifact; the ``manifest`` JSON column mirrors the parsed frontmatter.

Style follows ``routes/changelog.py`` + ``routes/intelligence.py``: deps
``get_async_db`` / ``current_user`` / ``get_current_organization``, async
``select`` reads, and **fail-soft** handlers — any error degrades to a safe
payload, never a 500. Flag-gated: when ``flags.AGENT_TEMPLATES`` is OFF the
gallery is inert (list = empty, mutations return a soft disabled payload).

Additive — the only core file touched is the router registration in main.py
(done by the parent, not here).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_db, get_current_organization
from app.core.auth import current_user
from app.models.user import User
from app.models.organization import Organization
from app.models.membership import Membership
from app.models.agent_template import AgentTemplate
from app.services.templates.parser import parse_frontmatter, validate_manifest
from app.services.templates.binder import preview_bind, run_instantiate
from app.services.templates.exporter import export_studio_to_template
from app.settings.hybrid_flags import flags as _flags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/templates", tags=["agent-templates"])


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _enabled() -> bool:
    return bool(getattr(_flags, "AGENT_TEMPLATES", False))


async def _is_org_admin(db: AsyncSession, user_id: str, org_id: str) -> bool:
    """True if the user is an admin/owner member of the org. Fail-soft → False."""
    try:
        res = await db.execute(
            select(Membership.role).where(
                Membership.user_id == user_id,
                Membership.organization_id == org_id,
            )
        )
        for (role,) in res.all():
            if role and str(role).lower() in ("admin", "owner"):
                return True
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates: admin check failed: %s", e)
    return False


def _manifest(t: AgentTemplate) -> dict:
    m = t.manifest if isinstance(t.manifest, dict) else {}
    return m


def _requires_columns(t: AgentTemplate) -> list:
    rc = _manifest(t).get("requires_columns")
    return rc if isinstance(rc, list) else []


def _card(t: AgentTemplate) -> dict:
    """Compact gallery-card shape."""
    m = _manifest(t)
    author = m.get("author") or ""
    uses = m.get("uses_skills") if isinstance(m.get("uses_skills"), list) else []
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "version": t.version,
        "description": t.description or "",
        "domain_tags": t.domain_tags if isinstance(t.domain_tags, list) else [],
        "scope": t.scope,
        "status": t.status,
        "author": author,
        "uses": len(uses),  # 0 for now (no install counter yet)
        "requires_columns": _requires_columns(t),
    }


def _detail(t: AgentTemplate) -> dict:
    d = _card(t)
    d.update({
        "body_md": t.body_md or "",
        "manifest": _manifest(t),
        "source_studio_id": t.source_studio_id,
        "author_user_id": t.author_user_id,
        "organization_id": t.organization_id,
        "created_at": t.created_at.isoformat() if isinstance(t.created_at, datetime) else None,
    })
    return d


# --------------------------------------------------------------------------- #
# GET /api/templates  — gallery list
# --------------------------------------------------------------------------- #
@router.get("")
async def list_templates(
    scope: str = Query("all", description="'org' | 'global' | 'all'"),
    q: Optional[str] = Query(None, description="search name/description/domain"),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Published templates visible to the caller's org + global, plus the
    caller's own drafts. Read-only, fail-soft."""
    if not _enabled():
        return {"templates": []}

    try:
        org_id = organization.id
        uid = current_user.id

        # Visibility: published org-rows for this org, OR published global rows,
        # OR the caller's own rows (any status, so drafts surface to their author).
        visibility = or_(
            (AgentTemplate.scope == "org")
            & (AgentTemplate.organization_id == org_id)
            & (AgentTemplate.status == "published"),
            (AgentTemplate.scope == "global") & (AgentTemplate.status == "published"),
            AgentTemplate.author_user_id == uid,
        )

        stmt = select(AgentTemplate).where(
            AgentTemplate.deleted_at.is_(None),
            visibility,
        )

        if scope == "org":
            stmt = stmt.where(AgentTemplate.scope == "org")
        elif scope == "global":
            stmt = stmt.where(AgentTemplate.scope == "global")
        # scope == "all" (or anything else) → no extra scope filter

        res = await db.execute(stmt.order_by(AgentTemplate.created_at.desc()))
        rows = list(res.scalars().all())

        if q:
            needle = q.strip().lower()
            if needle:
                def _match(t: AgentTemplate) -> bool:
                    hay = " ".join([
                        t.name or "",
                        t.description or "",
                        " ".join(t.domain_tags or []) if isinstance(t.domain_tags, list) else "",
                    ]).lower()
                    return needle in hay
                rows = [t for t in rows if _match(t)]

        return {"templates": [_card(t) for t in rows]}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.list_templates failed: %s", e)
        return {"templates": []}


# --------------------------------------------------------------------------- #
# POST /api/templates/from-studio/{studio_id}  — export a Studio -> draft template
# --------------------------------------------------------------------------- #
@router.post("/from-studio/{studio_id}")
async def export_from_studio(
    studio_id: str,
    payload: dict = Body(default={}),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Export a studio's data-agnostic know-how into a DRAFT AgentTemplate.
    Returns the new template detail (the caller can then Publish). Fail-soft."""
    if not _enabled():
        return {"disabled": True, "template": None}
    try:
        scope = (payload or {}).get("scope") or "org"
        if scope not in ("org", "global"):
            scope = "org"
        include_raw_sql = bool((payload or {}).get("include_raw_sql", False))
        t = await export_studio_to_template(
            db, studio_id=studio_id, author_user=current_user,
            organization=organization, scope=scope, include_raw_sql=include_raw_sql,
        )
        if t is None:
            return {"ok": False, "error": "export_failed", "template": None}
        return {"ok": True, "template": _detail(t)}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.export_from_studio(%s) failed: %s", studio_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": "unavailable", "template": None}


# --------------------------------------------------------------------------- #
# GET /api/templates/{id}/bind-preview  — auto-match column map for the wizard
# --------------------------------------------------------------------------- #
@router.get("/{template_id}/bind-preview")
async def bind_preview(
    template_id: str,
    data_source_id: str = Query(..., description="target data source to bind against"),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Propose a {as: column} map by matching the template's required roles to the
    target data source's profile_v2 roles. Read-only, fail-soft."""
    if not _enabled():
        return {"disabled": True, "column_map": {}, "needs_user": [], "requires_columns": []}
    try:
        return await preview_bind(
            db, template_id=template_id, data_source_id=data_source_id, organization=organization,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.bind_preview(%s) failed: %s", template_id, e)
        return {"column_map": {}, "needs_user": [], "requires_columns": []}


# --------------------------------------------------------------------------- #
# POST /api/templates/{id}/instantiate  — build a new Studio from a template
# --------------------------------------------------------------------------- #
@router.post("/{template_id}/instantiate")
async def instantiate(
    template_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Create a new Studio from a template, binding the template's placeholders to
    the caller's columns. Seeded rules/examples/metrics land PENDING. Fail-soft."""
    if not _enabled():
        return {"disabled": True, "studio_id": None}
    try:
        name = (payload or {}).get("name") or "New agent"
        data_source_ids = (payload or {}).get("data_source_ids") or []
        column_map = (payload or {}).get("column_map") or {}
        if not isinstance(data_source_ids, list) or not data_source_ids:
            return {"ok": False, "error": "data_source_ids required", "studio_id": None}
        studio = await run_instantiate(
            db, template_id=template_id, data_source_ids=data_source_ids,
            column_map=column_map, name=name, owner_user=current_user, organization=organization,
        )
        if studio is None:
            return {"ok": False, "error": "instantiate_failed", "studio_id": None}
        return {"ok": True, "studio_id": studio.id}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.instantiate(%s) failed: %s", template_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": "unavailable", "studio_id": None}


# --------------------------------------------------------------------------- #
# GET /api/templates/{id}  — detail
# --------------------------------------------------------------------------- #
@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Full template detail (body + manifest + requires_columns). Soft-404 when
    not visible. Read-only, fail-soft."""
    if not _enabled():
        return {"disabled": True, "template": None}

    try:
        res = await db.execute(
            select(AgentTemplate).where(
                AgentTemplate.id == template_id,
                AgentTemplate.deleted_at.is_(None),
            )
        )
        t = res.scalar_one_or_none()
        if t is None:
            return {"error": "not_found", "template": None}

        # Visibility check (mirror the list filter).
        visible = (
            t.author_user_id == current_user.id
            or (t.scope == "global" and t.status == "published")
            or (
                t.scope == "org"
                and t.organization_id == organization.id
                and t.status == "published"
            )
        )
        if not visible:
            return {"error": "not_found", "template": None}

        return {"template": _detail(t)}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.get_template(%s) failed: %s", template_id, e)
        return {"error": "unavailable", "template": None}


# --------------------------------------------------------------------------- #
# POST /api/templates/{id}/publish  — draft -> published
# --------------------------------------------------------------------------- #
@router.post("/{template_id}/publish")
async def publish_template(
    template_id: str,
    payload: dict = Body(default={}),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Flip a draft → published and set its scope. Author or org-admin only.
    Fail-soft."""
    if not _enabled():
        return {"disabled": True, "ok": False}

    try:
        scope = (payload or {}).get("scope") or "org"
        if scope not in ("org", "global"):
            scope = "org"

        res = await db.execute(
            select(AgentTemplate).where(
                AgentTemplate.id == template_id,
                AgentTemplate.deleted_at.is_(None),
            )
        )
        t = res.scalar_one_or_none()
        if t is None:
            return {"ok": False, "error": "not_found"}

        is_author = t.author_user_id == current_user.id
        is_admin = await _is_org_admin(db, current_user.id, organization.id)
        if not (is_author or is_admin):
            return {"ok": False, "error": "forbidden"}

        t.status = "published"
        t.scope = scope
        await db.commit()
        await db.refresh(t)
        return {"ok": True, "template": _detail(t)}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.publish_template(%s) failed: %s", template_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": "unavailable"}


# --------------------------------------------------------------------------- #
# POST /api/templates/import  — md -> draft row
# --------------------------------------------------------------------------- #
@router.post("/import")
async def import_template(
    payload: dict = Body(...),
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Parse an uploaded ``body_md`` → manifest, validate, persist a DRAFT row
    owned by the caller's org. Returns ``{id, manifest, problems}``. Fail-soft."""
    if not _enabled():
        return {"disabled": True, "id": None, "manifest": {}, "problems": ["feature disabled"]}

    try:
        body_md = (payload or {}).get("body_md") or ""
        if not isinstance(body_md, str) or not body_md.strip():
            return {"id": None, "manifest": {}, "problems": ["body_md is required"]}

        scope = (payload or {}).get("scope") or "org"
        if scope not in ("org", "global"):
            scope = "org"

        manifest = parse_frontmatter(body_md)
        ok, problems = validate_manifest(manifest)

        name = manifest.get("name") or "Untitled template"
        version = manifest.get("version") or "1.0.0"
        domain = manifest.get("domain") if isinstance(manifest.get("domain"), list) else []

        # stable-ish slug from the name
        import re as _re
        slug = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:160] or "template"

        t = AgentTemplate(
            name=name[:255],
            slug=slug,
            version=version[:20],
            description=(manifest.get("body") or "")[:500] or None,
            domain_tags=domain,
            scope=scope,
            status="draft",
            body_md=body_md,
            manifest=manifest,
            author_user_id=current_user.id,
            organization_id=organization.id,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)

        return {"id": t.id, "manifest": manifest, "problems": problems, "ok": ok}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.import_template failed: %s", e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"id": None, "manifest": {}, "problems": ["import failed"]}


# --------------------------------------------------------------------------- #
# DELETE /api/templates/{id}  — soft-delete own DRAFT only
# --------------------------------------------------------------------------- #
@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    """Soft-delete the caller's own DRAFT template. 403 (soft) if not owner or
    not a draft. Fail-soft."""
    if not _enabled():
        return {"disabled": True, "ok": False}

    try:
        res = await db.execute(
            select(AgentTemplate).where(
                AgentTemplate.id == template_id,
                AgentTemplate.deleted_at.is_(None),
            )
        )
        t = res.scalar_one_or_none()
        if t is None:
            return {"ok": False, "error": "not_found"}

        if t.author_user_id != current_user.id:
            return {"ok": False, "error": "forbidden"}
        if t.status != "draft":
            return {"ok": False, "error": "only drafts can be deleted"}

        t.deleted_at = datetime.utcnow()
        await db.commit()
        return {"ok": True, "id": template_id}
    except Exception as e:  # noqa: BLE001
        logger.warning("agent_templates.delete_template(%s) failed: %s", template_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": "unavailable"}
