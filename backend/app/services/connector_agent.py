"""Connector → Data Agent: make a connected connector an org-visible Data Agent.

bagofwords-style "the data source IS the agent". When an admin creates a
connection (flag ``HYBRID_CONNECTOR_AS_AGENT``), we ensure a DataSource wraps the
connection with ``is_public=True`` so every org member SEES it as an agent on the
``/agents`` page (that page lists DataSources; ``filter_user_visible_data_sources``
shows a member any ``is_public`` source). No Studio needed. For ``user_required``
connectors (e.g. Power BI user sign-in) each member still signs in with their own
account at first use — the shared source just surfaces the agent to everyone.

Design notes:
  * GREENLET: ``create_connection`` commits before calling us, which expires ORM
    objects. We take only primitive ids/strings and re-query fresh in our own
    session usage — never touch a caller-held expired object.
  * IDEMPOTENT: reusing the existing DataSource and only flipping ``is_public`` when
    needed is naturally idempotent — a 2nd call finds the public source and no-ops.
  * FAIL-SOFT: never raises. A failure here must not break connection creation.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.connection import Connection
from app.models.data_source import DataSource

logger = logging.getLogger(__name__)


async def auto_create_agent_for_connection(
    db: AsyncSession,
    *,
    connection_id: str,
    organization_id: str,
    owner_user_id: str,
) -> str | None:
    """Make a connection an org-visible Data Agent (a public DataSource).

    Idempotent, greenlet-safe, fail-soft. Returns the data_source id (existing or
    new), or None on any failure / flag-off. Caller passes primitive ids only.
    """
    try:
        from app.settings.hybrid_flags import flags
        if not getattr(flags, "CONNECTOR_AS_AGENT", False):
            return None

        # Re-query the connection fresh (caller's object may be expired post-commit).
        res = await db.execute(
            select(Connection)
            .options(selectinload(Connection.data_sources))
            .where(
                Connection.id == connection_id,
                Connection.organization_id == organization_id,
            )
        )
        conn = res.scalar_one_or_none()
        if conn is None:
            return None

        # Ensure a DataSource wraps the connection with is_public=True.
        ds_list = list(conn.data_sources or [])
        if ds_list:
            ds = ds_list[0]
            if not ds.is_public:
                ds.is_public = True
                await db.commit()
        else:
            ds = DataSource(
                name=conn.name,
                organization_id=organization_id,
                is_public=True,
                use_llm_sync=False,
                owner_user_id=owner_user_id,
            )
            ds.connections.append(conn)
            db.add(ds)
            try:
                await db.commit()
                await db.refresh(ds)
            except IntegrityError:
                await db.rollback()
                ds = DataSource(
                    name=f"{conn.name}-{str(conn.id)[:8]}",
                    organization_id=organization_id,
                    is_public=True,
                    use_llm_sync=False,
                    owner_user_id=owner_user_id,
                )
                ds.connections.append(conn)
                db.add(ds)
                await db.commit()
                await db.refresh(ds)

        logger.info(
            "connector-as-agent: org-visible data agent %s (data_source) for connection %s",
            ds.id, connection_id,
        )
        return str(ds.id)
    except Exception as e:  # noqa: BLE001 — must never break connection creation
        logger.warning("connector-as-agent auto-create failed for connection %s: %s", connection_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
