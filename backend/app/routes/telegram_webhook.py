"""Per-agent Telegram inbound webhook (HYBRID_AGENT_CHANNELS, default OFF).

Public (no auth dependency) endpoint Telegram calls with each update. Each agent
(`Studio`) can own its own Telegram bot via an ExternalPlatform(platform_type=
'telegram', studio_id=...). Verified org members (or anyone, if audience='anyone')
message the bot; we run the agent and reply with the final text answer.

Reuse decisions (no new infra):
  - Credentials: ExternalPlatform.encrypt_credentials / decrypt_credentials (Fernet
    via settings.dash_config.encryption_key) — same helper the slack/teams/email
    channels use.
  - Verification: ExternalUserMapping + ExternalUserMappingService.generate_
    verification_token / get_mapping_by_external_id (same as slack/teams/email).
  - Access: app.services.studio_access.resolve_studio_access (member-only audience).
  - Conversation: ReportService.create_report (Report bound to studio_id +
    external_platform_id) then CompletionService.create_completion — the SAME
    services the in-app chat uses. We run foreground (background=False) so we can
    read back the final answer text and reply synchronously (text-only v1).

The handler ALWAYS returns 200 {"ok": true} (Telegram retries on non-200).
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.dependencies import get_async_db
from app.models.external_platform import ExternalPlatform
from app.models.external_user_mapping import ExternalUserMapping
from app.models.report import Report
from app.models.completion import Completion
from app.settings.hybrid_flags import flags
from app.settings.config import settings
from app.services.studio_access import resolve_studio_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram-webhook"])


def _dash_base_url() -> str:
    import os
    return (
        os.environ.get("DASH_BASE_URL")
        or getattr(settings.dash_config, "base_url", None)
        or "http://0.0.0.0:3000"
    ).rstrip("/")


def _channel_bot_token(platform: ExternalPlatform) -> str | None:
    """Decrypt the Telegram bot token back from the encrypted credentials blob.

    Reuses ExternalPlatform.decrypt_credentials (Fernet, settings.dash_config.
    encryption_key) — same pathway as outbound sends for slack/teams.
    """
    try:
        return (platform.decrypt_credentials() or {}).get("bot_token")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to decrypt telegram bot token")
        return None


async def telegram_send(bot_token: str, chat_id, text: str) -> None:
    """Send a text message via the Telegram Bot API (best-effort)."""
    if not bot_token or chat_id is None:
        return
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4096]},
            )
    except Exception:  # noqa: BLE001
        logger.exception("telegram_send failed")


@router.post("/ext/telegram/{studio_id}/webhook")
async def telegram_webhook(studio_id: str, request: Request):
    """Inbound Telegram update for a per-agent bot. Always returns 200."""
    # Flag gate — 404-equivalent but still a 200 body so Telegram doesn't retry.
    if not flags.AGENT_CHANNELS:
        return {"ok": True}

    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": True}

    secret = request.query_params.get("secret")

    # Use our own session so we never depend on request-scoped teardown timing.
    async for db in get_async_db():
        try:
            await _handle_update(db, studio_id, secret, update)
        except Exception:  # noqa: BLE001
            logger.exception("telegram_webhook: handler failed for studio %s", studio_id)
        break

    return {"ok": True}


async def _handle_update(db, studio_id: str, secret: str | None, update: dict) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    frm = message.get("from") or {}
    chat = message.get("chat") or {}
    external_user_id = str(frm.get("id")) if frm.get("id") is not None else None
    username = frm.get("username") or frm.get("first_name")
    chat_id = chat.get("id")
    text = message.get("text") or ""

    if not external_user_id or chat_id is None:
        return

    # Resolve the active telegram channel for this studio.
    res = await db.execute(
        select(ExternalPlatform).where(
            ExternalPlatform.studio_id == studio_id,
            ExternalPlatform.platform_type == "telegram",
            ExternalPlatform.is_active.is_(True),
            ExternalPlatform.deleted_at.is_(None),
        )
    )
    platform = res.scalar_one_or_none()
    if platform is None:
        return

    # Secret check (reject mismatched callers — silently, with no reply).
    expected = (platform.platform_config or {}).get("secret")
    if not secret or not expected or secret != expected:
        logger.warning("telegram_webhook: bad secret for studio %s", studio_id)
        return

    bot_token = _channel_bot_token(platform)
    if not bot_token:
        return

    organization_id = platform.organization_id
    audience = getattr(platform, "audience", "members") or "members"

    app_user_id = None

    if audience == "members":
        # Look up (or create) the verification mapping for this telegram user.
        m_res = await db.execute(
            select(ExternalUserMapping).where(
                ExternalUserMapping.platform_id == str(platform.id),
                ExternalUserMapping.platform_type == "telegram",
                ExternalUserMapping.external_user_id == external_user_id,
            )
        )
        mapping = m_res.scalar_one_or_none()

        if mapping is None or not mapping.is_verified or not mapping.app_user_id:
            token = await _ensure_verification(db, platform, mapping, external_user_id, username)
            verify_link = f"{_dash_base_url()}/verify/{token}"
            await telegram_send(
                bot_token,
                chat_id,
                "To chat with this agent, please verify your account first:\n"
                f"{verify_link}\n\nAfter verifying, send your message again.",
            )
            return

        app_user_id = mapping.app_user_id
    else:
        # audience == 'anyone': no verification. Resolve a runner user (the studio
        # owner) so the agent runs with a valid identity + data-source access.
        from app.models.studio import Studio
        s_res = await db.execute(select(Studio).where(Studio.id == studio_id))
        studio = s_res.scalar_one_or_none()
        if studio is None:
            return
        app_user_id = studio.owner_user_id

    # Load the app user.
    from app.models.user import User
    u_res = await db.execute(select(User).where(User.id == app_user_id))
    user = u_res.scalar_one_or_none()
    if user is None:
        await telegram_send(bot_token, chat_id, "Your linked account could not be found.")
        return
    # studio_access reads user.organization_id; stamp it for the org-shared rung.
    if getattr(user, "organization_id", None) is None:
        try:
            user.organization_id = organization_id
        except Exception:  # noqa: BLE001
            pass

    # Confirm the resolved user still has access to this agent (members audience).
    if audience == "members":
        role = await resolve_studio_access(db, studio_id, user)
        if role is None:
            await telegram_send(bot_token, chat_id, "You no longer have access to this agent.")
            return

    if not text.strip():
        await telegram_send(bot_token, chat_id, "Please send a text question.")
        return

    answer = await _run_agent_answer(db, platform, studio_id, organization_id, user, text)
    await telegram_send(bot_token, chat_id, answer or "(no answer)")


async def _ensure_verification(db, platform, mapping, external_user_id, username) -> str:
    """Create/refresh an unverified mapping + return a fresh verification token."""
    import secrets as _secrets
    import datetime as _dt

    if mapping is None:
        mapping = ExternalUserMapping(
            organization_id=platform.organization_id,
            platform_id=str(platform.id),
            platform_type="telegram",
            external_user_id=external_user_id,
            external_name=username,
            is_verified=False,
        )
        db.add(mapping)

    token = _secrets.token_urlsafe(32)
    mapping.verification_token = token
    mapping.verification_expires_at = _dt.datetime.utcnow() + _dt.timedelta(hours=24)
    mapping.is_verified = False
    await db.commit()
    return token


async def _run_agent_answer(db, platform, studio_id, organization_id, user, text) -> str:
    """Create a studio-bound Report + run a completion; return the final text.

    Mirrors the in-app chat path: ReportService.create_report (studio_id +
    external_platform_id) -> CompletionService.create_completion(background=False)
    -> read back the latest system completion's text content.
    """
    from app.services.report_service import ReportService
    from app.services.completion_service import CompletionService
    from app.services.organization_service import OrganizationService
    from app.services.data_source_service import DataSourceService
    from app.schemas.report_schema import ReportCreate
    from app.schemas.completion_v2_schema import CompletionCreate, PromptSchema
    from app.models.organization import Organization

    org_res = await db.execute(select(Organization).where(Organization.id == organization_id))
    organization = org_res.scalar_one_or_none()
    if organization is None:
        return "Organization not found."

    # Data sources: studio pins are auto-merged by create_report (studio_id path);
    # also attach the user's accessible sources so DM-style chats work.
    try:
        data_sources = await DataSourceService().get_active_data_sources(db, organization, user)
        data_source_ids = [str(ds.id) for ds in data_sources]
    except Exception:  # noqa: BLE001
        data_source_ids = []

    report = await ReportService().create_report(
        db=db,
        report_data=ReportCreate(
            title=f"Telegram chat with {getattr(user, 'name', 'user')}",
            data_sources=data_source_ids,
            external_platform_id=str(platform.id),
            studio_id=studio_id,
        ),
        current_user=user,
        organization=organization,
    )
    await db.commit()

    await CompletionService().create_completion(
        db=db,
        report_id=str(report.id),
        completion_data=CompletionCreate(
            prompt=PromptSchema(
                content=text,
                widget_id=None,
                step_id=None,
                mentions=[
                    {"name": "MEMORY", "items": []},
                    {"name": "FILES", "items": []},
                    {"name": "DATA SOURCES", "items": []},
                ],
                platform="telegram",
            )
        ),
        current_user=user,
        organization=organization,
        background=False,  # run inline so we can return the final text
        external_user_id=str(getattr(user, "id", "")),
        external_platform="telegram",
        external_channel_id=str(report.id),
    )

    # Read back the latest system completion's final text for this report.
    c_res = await db.execute(
        select(Completion)
        .where(
            Completion.report_id == str(report.id),
            Completion.role == "system",
        )
        .order_by(Completion.created_at.desc())
        .limit(1)
    )
    completion = c_res.scalar_one_or_none()
    if completion is None:
        return "I couldn't generate an answer."
    content = (completion.completion or {}).get("content") if isinstance(completion.completion, dict) else None
    return content or "I couldn't generate an answer."
