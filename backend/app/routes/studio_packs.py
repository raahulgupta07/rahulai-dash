"""Domain Packs Phase 5 — promote a studio skill to the whole org.

A user/Teach-authored pack lives inline on ONE ``StudioBoundPack.pack_body``
(studio-scoped). Promoting copies that pack dict into the org-shared ``OrgPack``
store so EVERY studio in the org will autobind it at its next train (the
``pack_train`` autobind reads org packs alongside the yaml library). The shipped
yaml ``library`` stays immutable; org packs are the writable DB-backed extension.

Routes (no ``/api`` prefix — main.py mounts under /api):
  POST /studios/{studio_id}/packs/{pack_id}/promote   (editor+) -> upsert OrgPack
  GET  /organization/packs                            (viewer+) -> list org packs

Gated by ``flags.DOMAIN_PACKS`` (404 when off). Mirrors the deps/auth/role
helpers in ``studio_train`` / ``studio_teach``. NEVER 500s — fail-soft JSON.

NOTE: deliberately NO ``from __future__ import annotations``.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_user
from app.dependencies import get_async_db, get_current_organization
from app.errors import AppError, ErrorCode
from app.models.organization import Organization
from app.models.user import User
from app.models.studio import StudioBoundPack, OrgPack
from app.services.studio_access import resolve_studio_access
from app.settings.hybrid_flags import flags

router = APIRouter(tags=["studios"])

_EDITOR_ROLES = {"owner", "editor"}


def _require_flag() -> None:
    if not flags.DOMAIN_PACKS:
        raise AppError.not_found("studio.not_found", "Studio not found")


async def _require_role(db, studio_id, user, *, editor=False) -> str:
    role = await resolve_studio_access(db, studio_id, user)
    if role is None:
        raise AppError.not_found("studio.not_found", "Studio not found")
    if editor and role not in _EDITOR_ROLES:
        raise AppError.forbidden(ErrorCode.ACCESS_DENIED, "Editor or owner role required")
    return role


def _pack_name(pack_id: str, pack_body) -> str:
    """Human name for a bound-pack row: registry file, else inline body, else id."""
    try:
        from app.ai.packs import registry
        p = registry.get_pack(pack_id)
        if p and p.get("name"):
            return p["name"]
    except Exception:
        pass
    if isinstance(pack_body, dict) and pack_body.get("name"):
        return pack_body["name"]
    return pack_id


@router.get("/studios/{studio_id}/packs", response_model=dict)
async def list_studio_packs(
    studio_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List the studio's bound packs (viewer+), each with its binding, missing
    inputs, source and learned win-rate. Fail-soft empty list."""
    _require_flag()
    await _require_role(db, studio_id, current_user)
    try:
        from app.ai.packs import winrate as _wr

        rows = (
            await db.execute(
                select(StudioBoundPack).where(
                    StudioBoundPack.studio_id == str(studio_id),
                    StudioBoundPack.deleted_at.is_(None),
                ).order_by(StudioBoundPack.created_at.desc())
            )
        ).scalars().all()
        out = []
        for r in rows:
            score, samples = await _wr.get_winrate(db, str(studio_id), r.pack_id)
            out.append({
                "id": r.id,
                "pack_id": r.pack_id,
                "name": _pack_name(r.pack_id, r.pack_body),
                "status": r.status,
                "source": r.source,
                "conf": r.conf,
                "binding": r.binding_map or {},
                "missing": r.missing or [],
                "output_spec": r.output_spec or {},
                "method_text": (r.pack_body or {}).get("method_text") if isinstance(r.pack_body, dict) else None,
                "winrate": {"score": score, "samples": samples},
                "promotable": (r.source == "user" and isinstance(r.pack_body, dict)),
            })
        return {"ok": True, "packs": out}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "packs": []}


@router.post("/studios/{studio_id}/packs/{pack_id}/status", response_model=dict)
async def set_pack_status(
    studio_id: str,
    pack_id: str,
    payload: dict,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Approve / reject / reset a bound pack (editor+). Body {status:
    active|rejected|pending}. A pack can only go ACTIVE when it is fully bound
    (no missing required inputs) — a dormant pack must gain its columns first."""
    _require_flag()
    await _require_role(db, studio_id, current_user, editor=True)

    target = str((payload or {}).get("status") or "").strip().lower()
    if target not in {"active", "rejected", "pending"}:
        raise AppError.bad_request(
            ErrorCode.VALIDATION, "status must be active|rejected|pending")
    try:
        row = (
            await db.execute(
                select(StudioBoundPack).where(
                    StudioBoundPack.studio_id == str(studio_id),
                    StudioBoundPack.pack_id == str(pack_id),
                    StudioBoundPack.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if row is None:
            raise AppError.not_found("pack.not_found", "Pack not found on this studio")
        if target == "active" and (row.missing or []):
            raise AppError.bad_request(
                ErrorCode.VALIDATION,
                f"Cannot activate — unbound inputs: {', '.join(row.missing)}. "
                "Add the missing columns and re-train, then approve.",
            )
        row.status = target
        await db.commit()
        return {"ok": True, "pack_id": str(pack_id), "status": target}
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}


@router.post("/studios/{studio_id}/packs/{pack_id}/promote", response_model=dict)
async def promote_pack_to_org(
    studio_id: str,
    pack_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Copy a studio's user-authored pack into the org-shared store (editor+).

    Idempotent: re-promoting the same pack_id updates the stored body. The pack
    must carry an inline ``pack_body`` (i.e. a user/Teach or org pack); a bare
    library row (file-backed, no body) cannot be promoted — it already ships."""
    _require_flag()
    await _require_role(db, studio_id, current_user, editor=True)

    try:
        row = (
            await db.execute(
                select(StudioBoundPack).where(
                    StudioBoundPack.studio_id == str(studio_id),
                    StudioBoundPack.pack_id == str(pack_id),
                    StudioBoundPack.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if row is None:
            raise AppError.not_found("pack.not_found", "Pack not found on this studio")
        body = row.pack_body if isinstance(row.pack_body, dict) else None
        if not body:
            raise AppError.bad_request(
                ErrorCode.VALIDATION,
                "Only a user-authored pack (with an inline body) can be promoted; "
                "library packs already ship to every studio.",
            )

        org_id = str(organization.id)
        existing = (
            await db.execute(
                select(OrgPack).where(
                    OrgPack.organization_id == org_id,
                    OrgPack.pack_id == str(pack_id),
                    OrgPack.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.pack_body = body
            existing.status = "active"
            existing.source_studio_id = str(studio_id)
            action = "updated"
        else:
            db.add(OrgPack(
                organization_id=org_id,
                pack_id=str(pack_id),
                pack_body=body,
                status="active",
                source_studio_id=str(studio_id),
            ))
            action = "created"
        await db.commit()
        return {"ok": True, "action": action, "pack_id": str(pack_id),
                "name": body.get("name") or pack_id}
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001 - never 500
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}


@router.get("/organization/pack-analytics", response_model=dict)
async def org_pack_analytics(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Org-wide Domain Pack observability (any member). Aggregates:
      - per pack: fires, wins/losses/score, # studios bound, status counts
      - dormant backlog: which packs are dormant on which studio + missing cols
    Fail-soft. Gated by DOMAIN_PACKS."""
    _require_flag()
    try:
        from sqlalchemy import func
        from app.models.studio import StudioBoundPack, PackFireEvent, PackWinrate, Studio

        org_id = str(organization.id)
        # studio ids in this org (scope the pack tables, which key on studio_id)
        sids = (
            await db.execute(
                select(Studio.id).where(
                    Studio.organization_id == org_id, Studio.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        sids = [str(s) for s in sids]
        if not sids:
            return {"ok": True, "packs": [], "dormant": [], "totals": {}}

        # bound-pack rows (all statuses) for these studios
        rows = (
            await db.execute(
                select(StudioBoundPack).where(
                    StudioBoundPack.studio_id.in_(sids),
                    StudioBoundPack.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        # fires per pack
        fire_rows = (
            await db.execute(
                select(PackFireEvent.pack_id, func.count(PackFireEvent.id))
                .where(PackFireEvent.studio_id.in_(sids), PackFireEvent.deleted_at.is_(None))
                .group_by(PackFireEvent.pack_id)
            )
        ).all()
        fires = {str(p): int(c) for p, c in fire_rows}

        # win/loss per pack (sum across clusters/studios)
        wr_rows = (
            await db.execute(
                select(
                    PackWinrate.pack_id,
                    func.coalesce(func.sum(PackWinrate.passes), 0),
                    func.coalesce(func.sum(PackWinrate.fails), 0),
                )
                .where(PackWinrate.studio_id.in_(sids), PackWinrate.deleted_at.is_(None))
                .group_by(PackWinrate.pack_id)
            )
        ).all()
        wr = {str(p): (int(pa), int(fa)) for p, pa, fa in wr_rows}

        agg: dict = {}
        dormant: list = []
        for r in rows:
            a = agg.setdefault(r.pack_id, {
                "pack_id": r.pack_id, "name": _pack_name(r.pack_id, r.pack_body),
                "source": r.source, "studios": 0,
                "active": 0, "pending": 0, "dormant": 0, "rejected": 0,
            })
            a["studios"] += 1
            if r.status in a:
                a[r.status] += 1
            if r.status == "dormant":
                dormant.append({
                    "pack_id": r.pack_id, "name": _pack_name(r.pack_id, r.pack_body),
                    "studio_id": r.studio_id, "missing": r.missing or [],
                })

        packs = []
        for pid, a in agg.items():
            passes, fails = wr.get(pid, (0, 0))
            total = passes + fails
            a["fires"] = fires.get(pid, 0)
            a["wins"] = passes
            a["losses"] = fails
            a["win_rate"] = round(passes / total, 3) if total else None
            a["samples"] = total
            packs.append(a)
        packs.sort(key=lambda x: (-(x["fires"] or 0), -(x["samples"] or 0)))

        totals = {
            "packs": len(packs),
            "active": sum(a["active"] for a in packs),
            "dormant": len(dormant),
            "fires": sum(fires.values()),
            "studios_with_packs": len({r.studio_id for r in rows}),
        }
        return {"ok": True, "packs": packs, "dormant": dormant, "totals": totals}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "packs": [], "dormant": [], "totals": {}}


@router.get("/organization/packs", response_model=dict)
async def list_org_packs(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """List the org-shared packs (viewer+). Fail-soft empty list."""
    _require_flag()
    try:
        rows = (
            await db.execute(
                select(OrgPack).where(
                    OrgPack.organization_id == str(organization.id),
                    OrgPack.deleted_at.is_(None),
                ).order_by(OrgPack.created_at.desc())
            )
        ).scalars().all()
        return {"ok": True, "packs": [
            {"pack_id": r.pack_id, "name": (r.pack_body or {}).get("name") or r.pack_id,
             "status": r.status, "source_studio_id": r.source_studio_id}
            for r in rows
        ]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "packs": []}


_CATEGORY_BY_ID = {
    # Performance & operating analytics
    "ebitda-good-bad-ugly": "Performance",
    "variance-commentary": "Performance",
    "unit-economics": "Performance",
    # Valuation (market-data dependent)
    "comps-analysis": "Valuation",
    "dcf-valuation": "Valuation",
    "earnings-vs-consensus": "Valuation",
    # Fund / PE / portfolio
    "returns-analysis": "Fund / PE",
    "nav-tie-out": "Fund / PE",
    "portfolio-monitoring": "Fund / PE",
    # Accounting / close
    "gl-reconciliation": "Accounting",
    "three-statement-integrity": "Accounting",
    # Output / deliverables
    "pptx-author": "Output",
    "xlsx-author": "Output",
    "teaser-builder": "Output",
    "deck-refresh": "Output",
}


def _category_for(pack: dict) -> str:
    """Curated analytical category for the Skills rail (by pack id, then domain
    prefix fallback). Distinct from tier (which is data-readiness)."""
    pid = str(pack.get("id") or "")
    if pid in _CATEGORY_BY_ID:
        return _CATEGORY_BY_ID[pid]
    dom = str(pack.get("domain") or "")
    if dom.startswith("finance."):
        return "Finance"
    return "General"


def _tier_for(pack: dict) -> str:
    """Best-effort tier label from the pack's domain / inputs. Tier A runs on our
    data, Tier C is output-only (no measure inputs), Tier B needs an external feed
    (declares a non-optional input the warehouse won't have, e.g. peer multiples)."""
    pid = str(pack.get("id") or "")
    feed = {"comps-analysis", "dcf-valuation", "earnings-vs-consensus"}
    out = {"pptx-author", "xlsx-author", "teaser-builder", "deck-refresh"}
    if pid in feed:
        return "B"
    if pid in out:
        return "C"
    return "A"


@router.get("/packs/library", response_model=dict)
async def list_pack_library(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    """Global catalog of every Domain Pack the platform ships (the yaml library)
    plus this org's DB-backed org packs — for the Build → Skills page. Each entry
    carries its domain, tier, trigger hints, required inputs, and how many studios
    in this org have it bound (active count). Read-only, fail-soft. Gated by
    DOMAIN_PACKS so the section hides when the feature is off."""
    _require_flag()
    try:
        from app.ai.packs import registry
        from app.models.studio import StudioBoundPack, Studio

        org_id = str(organization.id)
        # bound counts per pack across this org (active vs any), for the "in use" chip
        sids = (
            await db.execute(
                select(Studio.id).where(
                    Studio.organization_id == org_id, Studio.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        sids = [str(s) for s in sids]
        bound: dict = {}
        if sids:
            rows = (
                await db.execute(
                    select(StudioBoundPack.pack_id, StudioBoundPack.status)
                    .where(StudioBoundPack.studio_id.in_(sids), StudioBoundPack.deleted_at.is_(None))
                )
            ).all()
            for pid_, st_ in rows:
                t, a = bound.get(str(pid_), (0, 0))
                bound[str(pid_)] = (t + 1, a + (1 if st_ == "active" else 0))

        def _inputs(pack: dict) -> list:
            out = []
            for key, spec in (pack.get("required_inputs") or {}).items():
                spec = spec if isinstance(spec, dict) else {}
                out.append({
                    "key": key,
                    "role": spec.get("role") or "any",
                    "optional": bool(spec.get("optional")),
                    "desc": spec.get("desc") or "",
                })
            return out

        catalog = []
        for pack in registry.list_packs():
            pid = str(pack.get("id") or "")
            b_total, b_active = bound.get(pid, (0, 0))
            catalog.append({
                "pack_id": pid,
                "name": pack.get("name") or pid,
                "domain": pack.get("domain") or "general",
                "tier": _tier_for(pack),
                "category": _category_for(pack),
                "source": "library",
                "triggers": (pack.get("trigger_hints") or [])[:12],
                "inputs": _inputs(pack),
                "output": ((pack.get("output_spec") or {}) if isinstance(pack.get("output_spec"), dict) else {}).get("format") or pack.get("format") or "",
                "bound_studios": b_total,
                "active_studios": b_active,
            })

        # org packs (DB-backed, user-promoted)
        org_rows = (
            await db.execute(
                select(OrgPack).where(
                    OrgPack.organization_id == org_id, OrgPack.deleted_at.is_(None)
                ).order_by(OrgPack.created_at.desc())
            )
        ).scalars().all()
        for r in org_rows:
            body = r.pack_body if isinstance(r.pack_body, dict) else {}
            pid = str(r.pack_id)
            b_total, b_active = bound.get(pid, (0, 0))
            catalog.append({
                "pack_id": pid,
                "name": body.get("name") or pid,
                "domain": body.get("domain") or "general",
                "tier": "Org",
                "category": "Org",
                "source": "org",
                "triggers": (body.get("trigger_hints") or [])[:12],
                "inputs": _inputs(body),
                "output": "",
                "bound_studios": b_total,
                "active_studios": b_active,
                "status": r.status,
            })

        catalog.sort(key=lambda x: (x["tier"], x["name"].lower()))
        totals = {
            "total": len(catalog),
            "library": sum(1 for c in catalog if c["source"] == "library"),
            "org": sum(1 for c in catalog if c["source"] == "org"),
            "in_use": sum(1 for c in catalog if c["active_studios"] > 0),
        }
        return {"ok": True, "packs": catalog, "totals": totals}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "packs": [], "totals": {}}
