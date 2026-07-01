"""Per-user private connector (HYBRID_PER_USER_CONNECTOR).

Admin configures a connector ONCE as a TEMPLATE (a DataSource with
`is_user_template=True` — tenant/client config on its Connection, NO user creds,
NO synced data). Each member then *registers* against that template with their
own credentials. Registration CLONES the template into a private, owner-scoped
DataSource (+ its own Connection) and syncs the catalog under the member's own
token — so every user gets ONLY the tables their account can see, private to
them (`is_public=False` + `owner_user_id` + the source's own access control).

Isolation is triple-gated and reuses primitives that already exist:
  * new private Connection (owner_user_id=user) carrying the user's OWN creds
    (Fernet at rest) — 1:1 with the user, so no shared/system credentials
  * refresh_schema — catalog fetched under the user's own credentials
  * is_public=False + owner membership — clone visible only to its owner

Everything here is additive + fail-soft; the template row is never mutated.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.data_source import DataSource
from app.models.connection import Connection
from app.models.organization import Organization
from app.models.user import User
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)


async def list_available_templates(db, organization: Organization) -> list[dict]:
    """Templates a member can self-register against (admin-published shells)."""
    if not flags.PER_USER_CONNECTOR:
        return []
    rows = (
        await db.execute(
            select(DataSource)
            .options(selectinload(DataSource.connections))
            .where(
                DataSource.organization_id == str(organization.id),
                DataSource.is_user_template.is_(True),
            )
        )
    ).scalars().all()

    out: list[dict] = []
    for ds in rows:
        if (getattr(ds, "publish_status", "published") or "published") == "disabled":
            continue
        conn = ds.connections[0] if ds.connections else None
        out.append({
            "id": str(ds.id),
            "name": ds.name,
            "description": ds.description or "",
            "type": conn.type if conn else None,
            "auth_policy": conn.auth_policy if conn else None,
            "allowed_user_auth_modes": (conn.allowed_user_auth_modes if conn else None) or [],
        })
    return out


async def _existing_clone(db, *, template_id: str, user_id: str) -> Optional[DataSource]:
    return (
        await db.execute(
            select(DataSource)
            .options(selectinload(DataSource.connections))
            .where(
                DataSource.template_source_id == str(template_id),
                DataSource.owner_user_id == str(user_id),
            )
        )
    ).scalars().first()


async def register_template_for_user(
    db,
    *,
    template_id: str,
    organization: Organization,
    user: User,
    auth_mode: str,
    credentials: dict,
) -> DataSource:
    """Clone a template into a private data source for `user` and sync under
    their own credentials. Idempotent per (template, user): re-registering
    updates the stored credentials and re-syncs the same private clone."""
    if not flags.PER_USER_CONNECTOR:
        raise HTTPException(status_code=404, detail="Per-user connector is not enabled")

    # Capture primitives up-front — the commits below expire ORM objects (greenlet).
    org_id = str(organization.id)
    user_id = str(user.id)

    template = (
        await db.execute(
            select(DataSource)
            .options(selectinload(DataSource.connections))
            .where(
                DataSource.id == str(template_id),
                DataSource.organization_id == org_id,
            )
        )
    ).scalars().first()
    if not template or not template.is_user_template:
        raise HTTPException(status_code=404, detail="Connector template not found")
    if not template.connections:
        raise HTTPException(status_code=400, detail="Connector template has no connection")

    tmpl_conn = template.connections[0]
    conn_type = tmpl_conn.type
    tmpl_config = tmpl_conn.config
    if isinstance(tmpl_config, str):
        try:
            tmpl_config = json.loads(tmpl_config)
        except Exception:
            tmpl_config = {}
    tmpl_config = dict(tmpl_config or {})
    tmpl_name = template.name
    creds = dict(credentials or {})

    # The per-user clone connection is 1:1 private to this user, so we store the
    # user's OWN credentials directly on it as system_only creds (Fernet at rest).
    # This is what refresh_schema (connection-level) AND the chat credential
    # resolver both read — no two-level per-user credential dance needed. The
    # data is still fully isolated: the connection is owner_user_id-private and
    # only this user's is_public=False DataSource points to it.

    # Re-registration → reuse the existing private clone; refresh its creds.
    clone = await _existing_clone(db, template_id=str(template_id), user_id=user_id)
    if clone is not None:
        new_conn = clone.connections[0] if clone.connections else None
        if new_conn is not None and creds:
            new_conn.credentials = None
            new_conn.encrypt_credentials(creds)
            new_conn.auth_policy = "system_only"
            db.add(new_conn)
            await db.commit()
            await db.refresh(new_conn)
    else:
        # 1. Private per-user connection carrying the user's own credentials.
        #    system_only → create_connection validates them up-front (bad creds
        #    surface as a 400 to the user) and kicks off catalog indexing.
        from app.services.connection_service import ConnectionService
        conn_svc = ConnectionService()
        base_name = f"{tmpl_name} · {user.email or user_id[:8]}"
        new_conn = None
        for attempt in range(4):
            name_try = base_name if attempt == 0 else f"{base_name} ({attempt+1})"
            try:
                new_conn = await conn_svc.create_connection(
                    db=db,
                    organization=organization,
                    current_user=user,
                    name=name_try,
                    type=conn_type,
                    config=dict(tmpl_config),
                    credentials=creds,
                    auth_policy="system_only",
                    owner_user_id=user_id,
                    # Identity already proven via device-code; tolerate an empty /
                    # non-queryable catalog at connect (Power BI on-prem datasets,
                    # etc.). The catalog syncs best-effort below.
                    validate=False,
                )
                break
            except HTTPException as e:
                if e.status_code == 409 and attempt < 3:
                    continue
                raise
        if new_conn is None:
            raise HTTPException(status_code=409, detail="Could not create your connection")

        # 2. Private, owner-scoped DataSource clone bound to that connection.
        clone = None
        for attempt in range(4):
            ds_name = base_name if attempt == 0 else f"{base_name} ({attempt+1})"
            clone = DataSource(
                name=ds_name,
                organization_id=org_id,
                owner_user_id=user_id,
                is_public=False,
                is_user_template=False,
                template_source_id=str(template_id),
                # Auto-learn ON: after the catalog syncs, a background task runs
                # llm_sync() to generate the description + conversation starters +
                # a primary "overview" instruction — same as the manual wizard's
                # "Use LLM to learn agent". See autolearn_clone() below.
                use_llm_sync=True,
            )
            clone.connections.append(new_conn)
            db.add(clone)
            try:
                await db.commit()
                await db.refresh(clone)
                break
            except IntegrityError:
                await db.rollback()
                clone = None
        if clone is None:
            raise HTTPException(status_code=409, detail="Could not create your private data source")

        # 3. Owner membership so it appears in the owner's agents list.
        try:
            from app.services.data_source_service import DataSourceService
            await DataSourceService()._create_memberships(db, clone, [user_id], permissions=["manage"])
        except Exception as e:
            logger.warning("per_user_connector: membership create failed: %s", e)

    # 4. Sync the catalog under the user's own creds → private per-user tables.
    clone_id = str(clone.id)
    if new_conn is not None:
        try:
            from app.services.connection_service import ConnectionService
            await ConnectionService().refresh_schema(db, new_conn, current_user=user)
            # Seed DataSourceTable from the freshly-synced ConnectionTable catalog.
            fresh = (
                await db.execute(
                    select(DataSource)
                    .options(selectinload(DataSource.connections))
                    .where(DataSource.id == clone_id)
                )
            ).scalars().first()
            if fresh and fresh.connections:
                await DataSourceService_seed(db, fresh, fresh.connections[0])
        except Exception as e:
            # Fail-soft: the clone + creds exist; the user can re-sync from the UI.
            logger.warning("per_user_connector: initial sync failed for %s: %s", clone_id, e)

    return (
        await db.execute(
            select(DataSource)
            .options(selectinload(DataSource.connections))
            .where(DataSource.id == clone_id)
        )
    ).scalars().first()


# --- Device-code sign-in (MFA-safe, no app registration) --------------------
# For Microsoft connectors a member proves identity via the OAuth device-code
# flow instead of typing a password: we show a short code + verification URL,
# they approve on any device (MFA happens there), and we poll until a
# refresh_token comes back — then auto-register their private clone with it.

# Device-code scope per connector type (all share the FOCI public client).
_DEVICE_CODE_SCOPE = {
    "ms_fabric": "SCOPE_FABRIC",
    "ms_fabric_user": "SCOPE_FABRIC",
    "powerbi": "SCOPE_POWERBI",
    "powerbi_user": "SCOPE_POWERBI",
    "sharepoint": "SCOPE_GRAPH",
    "onedrive": "SCOPE_GRAPH",
}


async def _template_tenant_and_scope(db, *, template_id: str, organization: Organization):
    """Load a template and derive (tenant_id, scope_const_name, conn_type) for
    the device-code flow. Raises 404 if not a valid template."""
    org_id = str(organization.id)
    template = (
        await db.execute(
            select(DataSource)
            .options(selectinload(DataSource.connections))
            .where(
                DataSource.id == str(template_id),
                DataSource.organization_id == org_id,
            )
        )
    ).scalars().first()
    if not template or not template.is_user_template or not template.connections:
        raise HTTPException(status_code=404, detail="Connector template not found")
    conn = template.connections[0]
    conn_type = conn.type
    scope_name = _DEVICE_CODE_SCOPE.get(conn_type)
    if not scope_name:
        raise HTTPException(
            status_code=400,
            detail=f"Device-code sign-in is not supported for '{conn_type}'",
        )
    cfg = conn.config
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}
    cfg = dict(cfg or {})
    # tenant_id may live on config or on the stored (admin) credentials; fall
    # back to the multi-tenant "organizations" endpoint (works for FOCI).
    tenant_id = cfg.get("tenant_id")
    if not tenant_id:
        try:
            saved = conn.decrypt_credentials() or {}
            tenant_id = saved.get("tenant_id")
        except Exception:
            tenant_id = None
    return (tenant_id or "organizations"), scope_name, conn_type


async def device_code_start(db, *, template_id: str, organization: Organization) -> dict:
    """Begin device-code sign-in for a template. Returns user_code + URL to show."""
    if not flags.PER_USER_CONNECTOR:
        raise HTTPException(status_code=404, detail="Per-user connector is not enabled")
    tenant_id, scope_name, _ = await _template_tenant_and_scope(
        db, template_id=template_id, organization=organization
    )
    from app.services import powerbi_device_code as dc
    scope = getattr(dc, scope_name)
    res = dc.start_device_code(tenant_id, scope=scope)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Could not start sign-in"))
    # Do NOT leak the tenant back; the poll route re-derives it from the template.
    return {
        "user_code": res.get("user_code"),
        "verification_uri": res.get("verification_uri"),
        "device_code": res.get("device_code"),
        "expires_in": res.get("expires_in"),
        "interval": res.get("interval"),
        "message": res.get("message"),
    }


async def device_code_poll(
    db, *, template_id: str, organization: Organization, user: User, device_code: str
) -> dict:
    """Poll once. On success, auto-register the caller's private clone with the
    returned refresh_token and return the created data source id."""
    if not flags.PER_USER_CONNECTOR:
        raise HTTPException(status_code=404, detail="Per-user connector is not enabled")
    tenant_id, _, _ = await _template_tenant_and_scope(
        db, template_id=template_id, organization=organization
    )
    from app.services import powerbi_device_code as dc
    res = dc.poll_device_code(tenant_id, device_code)
    status = res.get("status")
    if status == "pending":
        return {"status": "pending", "slow_down": bool(res.get("slow_down"))}
    if status != "success":
        return {"status": "error", "error": res.get("error", "Sign-in failed")}

    refresh_token = res.get("refresh_token")
    if not refresh_token:
        return {"status": "error", "error": "No refresh token returned — offline_access scope missing"}

    creds = {"refresh_token": refresh_token}
    if tenant_id and tenant_id != "organizations":
        creds["tenant_id"] = tenant_id
    clone = await register_template_for_user(
        db,
        template_id=template_id,
        organization=organization,
        user=user,
        auth_mode="device_code",
        credentials=creds,
    )
    return {"status": "success", "data_source_id": str(clone.id) if clone else None}


async def autolearn_clone(clone_id: str, org_id: str, user_id: str) -> None:
    """Background task: generate description + conversation starters + a primary
    overview instruction for a freshly-created connector clone — identical to the
    manual wizard's "Use LLM to learn agent". Runs in its own DB session (the
    request session is already closed by the time this fires) and is fully
    fail-soft: the agent works without it; the user can re-learn from the UI."""
    from app.dependencies import async_session_maker
    try:
        async with async_session_maker() as db:
            org = (
                await db.execute(select(Organization).where(Organization.id == str(org_id)))
            ).scalars().first()
            if not org:
                return
            user = (
                await db.execute(select(User).where(User.id == str(user_id)))
            ).scalars().first()
            from app.services.data_source_service import DataSourceService
            # llm_sync respects the clone's use_llm_sync flag (now True) and fills
            # description / conversation_starters / primary_instruction draft.
            await DataSourceService().llm_sync(db, str(clone_id), org, user)
    except Exception as e:
        logger.warning("per_user_connector: autolearn failed for %s: %s", clone_id, e)


async def DataSourceService_seed(db, data_source: DataSource, connection: Connection) -> None:
    """Seed DataSourceTable rows from a connection's ConnectionTable catalog."""
    from app.services.data_source_service import DataSourceService
    svc = DataSourceService()
    # Auto-activate ALL synced tables so the private clone is chat-ready the
    # instant sign-in completes — no manual Select-Tables step. The user only
    # ever sees the tables their OWN account could read, so activating all of
    # them is correct (the sign-in already scoped the catalog). max_auto_select
    # activates every table when total <= the limit, so pass a high ceiling.
    await svc.sync_domain_tables_from_connection(
        db, data_source, connection, max_auto_select=100000
    )
    await db.commit()
