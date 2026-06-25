from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.dependencies import get_async_db
from app.models.user import User
from app.models.organization import Organization
from app.core.auth import current_user
from app.dependencies import get_current_organization
from app.core.permissions_decorator import requires_permission
from app.services.external_platform_service import ExternalPlatformService
from app.schemas.external_platform_schema import (
    ExternalPlatformCreate,
    ExternalPlatformUpdate,
    ExternalPlatformSchema,
    SlackConfig,
    TeamsConfig,
    WhatsAppConfig,
    EmailConfig,
)
from app.models.external_platform import ExternalPlatform
from app.ee.audit.service import audit_service

# HYBRID_AGENT_CHANNELS: per-agent (Studio) Telegram channels.
import secrets as _secrets
import httpx as _httpx
from pydantic import BaseModel as _BaseModel, Field as _Field
from sqlalchemy import select as _select
from app.settings.hybrid_flags import flags as _flags
from app.settings.config import settings as _settings
from app.services.studio_access import resolve_studio_access as _resolve_studio_access

router = APIRouter(tags=["organization_settings"])
external_platform_service = ExternalPlatformService()


def _dash_base_url() -> str:
    """Public base URL used for Telegram webhook + verify links."""
    import os as _os
    return (
        _os.environ.get("DASH_BASE_URL")
        or getattr(_settings.dash_config, "base_url", None)
        or "http://0.0.0.0:3000"
    ).rstrip("/")


def _redact_channel(platform: ExternalPlatform) -> dict:
    """Serialize an ExternalPlatform channel row with credentials redacted."""
    cfg = dict(platform.platform_config or {})
    cfg.pop("secret", None)  # never expose the webhook secret
    return {
        "id": str(platform.id),
        "platform_type": platform.platform_type,
        "studio_id": getattr(platform, "studio_id", None),
        "audience": getattr(platform, "audience", "members"),
        "is_active": bool(platform.is_active),
        "platform_config": cfg,
        "has_credentials": bool(platform.credentials),
        "created_at": platform.created_at,
    }


class TelegramChannelCreate(_BaseModel):
    bot_token: str
    audience: str = _Field(default="members", pattern="^(members|anyone)$")


async def _require_channel_manager(db, studio_id: str, user):
    """Owner/editor only for channel management. Raises 403 otherwise."""
    role = await _resolve_studio_access(db, studio_id, user)
    if role not in ("owner", "editor"):
        raise HTTPException(status_code=403, detail="You do not have access to manage this agent's channels.")
    return role


@router.post("/studios/{studio_id}/channels/telegram")
async def create_telegram_channel(
    studio_id: str,
    data: TelegramChannelCreate,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Attach a per-agent Telegram bot to a Studio (HYBRID_AGENT_CHANNELS)."""
    if not _flags.AGENT_CHANNELS:
        raise HTTPException(status_code=404, detail="Not found")
    await _require_channel_manager(db, studio_id, current_user)

    secret = _secrets.token_urlsafe(24)
    platform = ExternalPlatform(
        organization_id=organization.id,
        platform_type="telegram",
        platform_config={"secret": secret},
        studio_id=studio_id,
        audience=data.audience,
        is_active=True,
    )
    platform.encrypt_credentials({"bot_token": data.bot_token})

    db.add(platform)
    await db.commit()
    await db.refresh(platform)

    # Best-effort: register the webhook with Telegram. Save the row regardless.
    warning = None
    webhook_url = f"{_dash_base_url()}/api/ext/telegram/{studio_id}/webhook?secret={secret}"
    try:
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{data.bot_token}/setWebhook",
                json={"url": webhook_url},
            )
            body = resp.json()
            if resp.status_code != 200 or not body.get("ok"):
                warning = f"setWebhook failed: {body.get('description') or resp.status_code}"
    except Exception as e:  # noqa: BLE001
        warning = f"setWebhook error: {e}"

    out = _redact_channel(platform)
    out["webhook_url"] = webhook_url
    if warning:
        out["warning"] = warning
    return out


@router.get("/studios/{studio_id}/channels")
async def list_studio_channels(
    studio_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """List channels bound to a Studio (credentials redacted)."""
    if not _flags.AGENT_CHANNELS:
        raise HTTPException(status_code=404, detail="Not found")
    # Any role with studio access may view the channel list.
    role = await _resolve_studio_access(db, studio_id, current_user)
    if role is None:
        raise HTTPException(status_code=403, detail="You do not have access to this agent.")

    res = await db.execute(
        _select(ExternalPlatform).where(
            ExternalPlatform.studio_id == studio_id,
            ExternalPlatform.organization_id == organization.id,
            ExternalPlatform.deleted_at.is_(None),
        )
    )
    return [_redact_channel(p) for p in res.scalars().all()]


async def _get_studio_channel(db, studio_id: str, channel_id: str, organization) -> ExternalPlatform:
    res = await db.execute(
        _select(ExternalPlatform).where(
            ExternalPlatform.id == channel_id,
            ExternalPlatform.studio_id == studio_id,
            ExternalPlatform.organization_id == organization.id,
            ExternalPlatform.deleted_at.is_(None),
        )
    )
    platform = res.scalar_one_or_none()
    if platform is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return platform


@router.post("/studios/{studio_id}/channels/{channel_id}/enable")
async def enable_studio_channel(
    studio_id: str,
    channel_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    if not _flags.AGENT_CHANNELS:
        raise HTTPException(status_code=404, detail="Not found")
    await _require_channel_manager(db, studio_id, current_user)
    platform = await _get_studio_channel(db, studio_id, channel_id, organization)
    platform.is_active = True
    await db.commit()
    await db.refresh(platform)
    return _redact_channel(platform)


@router.post("/studios/{studio_id}/channels/{channel_id}/disable")
async def disable_studio_channel(
    studio_id: str,
    channel_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    if not _flags.AGENT_CHANNELS:
        raise HTTPException(status_code=404, detail="Not found")
    await _require_channel_manager(db, studio_id, current_user)
    platform = await _get_studio_channel(db, studio_id, channel_id, organization)
    platform.is_active = False
    await db.commit()
    await db.refresh(platform)
    return _redact_channel(platform)


@router.delete("/studios/{studio_id}/channels/{channel_id}")
async def delete_studio_channel(
    studio_id: str,
    channel_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db),
):
    """Soft-delete a channel + best-effort deleteWebhook with Telegram."""
    if not _flags.AGENT_CHANNELS:
        raise HTTPException(status_code=404, detail="Not found")
    await _require_channel_manager(db, studio_id, current_user)
    platform = await _get_studio_channel(db, studio_id, channel_id, organization)

    # Best-effort deleteWebhook before tearing down (telegram only).
    if platform.platform_type == "telegram":
        try:
            bot_token = (platform.decrypt_credentials() or {}).get("bot_token")
            if bot_token:
                async with _httpx.AsyncClient(timeout=15.0) as client:
                    await client.post(f"https://api.telegram.org/bot{bot_token}/deleteWebhook")
        except Exception:  # noqa: BLE001
            pass

    import datetime as _dt
    platform.deleted_at = _dt.datetime.utcnow()
    platform.is_active = False
    await db.commit()
    return {"success": True}

@router.get("/settings/integrations", response_model=List[ExternalPlatformSchema])
@requires_permission('manage_settings')
async def get_integrations(
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Get all integrations for an organization"""
    return await external_platform_service.get_platforms(db, organization)

@router.get("/settings/integrations/{platform_id}", response_model=ExternalPlatformSchema)
@requires_permission('manage_settings', model=ExternalPlatform)
async def get_integration(
    platform_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Get a specific integration"""
    platform = await external_platform_service.get_platform_by_id(
        db, platform_id, organization
    )
    return ExternalPlatformSchema.from_orm(platform)

@router.put("/settings/integrations/{platform_id}", response_model=ExternalPlatformSchema)
@requires_permission('manage_settings', model=ExternalPlatform)
async def update_integration(
    platform_id: str,
    platform_data: ExternalPlatformUpdate,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Update an integration"""
    return await external_platform_service.update_platform(
        db, platform_id, platform_data, organization
    )

@router.delete("/settings/integrations/{platform_id}")
@requires_permission('manage_settings', model=ExternalPlatform)
async def delete_integration(
    platform_id: str,
    request: Request,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete an integration"""
    result = await external_platform_service.delete_platform(
        db, platform_id, organization
    )
    try:
        await audit_service.log(
            db=db,
            organization_id=organization.id,
            action="integration.deleted",
            user_id=current_user.id,
            resource_type="integration",
            resource_id=platform_id,
            request=request,
        )
    except Exception:
        pass
    return result

@router.post("/settings/integrations/{platform_id}/test", response_model=dict)
@requires_permission('manage_settings', model=ExternalPlatform)
async def test_integration(
    platform_id: str,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Test connection to an integration"""
    return await external_platform_service.test_platform_connection(
        db, platform_id, organization
    )

@router.post("/settings/integrations/slack", response_model=ExternalPlatformSchema)
@requires_permission('manage_settings')
async def create_slack_integration(
    data: SlackConfig,
    request: Request,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new Slack integration"""
    result = await external_platform_service.create_slack_platform(
        db, organization, data.bot_token, data.signing_secret, current_user,
        auto_link_by_email=data.auto_link_by_email,
    )
    try:
        await audit_service.log(
            db=db,
            organization_id=organization.id,
            action="integration.created",
            user_id=current_user.id,
            resource_type="integration",
            resource_id=result.id if hasattr(result, "id") else None,
            details={"type": "slack"},
            request=request,
        )
    except Exception:
        pass
    return result

@router.post("/settings/integrations/whatsapp", response_model=ExternalPlatformSchema)
@requires_permission('manage_settings')
async def create_whatsapp_integration(
    data: WhatsAppConfig,
    request: Request,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new WhatsApp integration"""
    result = await external_platform_service.create_whatsapp_platform(
        db,
        organization,
        data.access_token,
        data.phone_number_id,
        data.waba_id,
        data.app_secret,
        data.verify_token,
        current_user,
    )
    try:
        await audit_service.log(
            db=db,
            organization_id=organization.id,
            action="integration.created",
            user_id=current_user.id,
            resource_type="integration",
            resource_id=result.id if hasattr(result, "id") else None,
            details={"type": "whatsapp"},
            request=request,
        )
    except Exception:
        pass
    return result

@router.post("/settings/integrations/email/test", response_model=dict)
@requires_permission('manage_settings')
async def test_email_config(
    data: EmailConfig,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Test email credentials WITHOUT saving the integration.

    Backs the setup form's pre-save "Test connection" button. Returns
    ``{success, smtp, imap}``.
    """
    return await external_platform_service.test_email_config(data)

@router.post("/settings/integrations/email", response_model=ExternalPlatformSchema)
@requires_permission('manage_settings')
async def create_email_integration(
    data: EmailConfig,
    request: Request,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new Email integration.

    SMTP-only configures the org's outbound mail transport. Providing IMAP
    fields additionally turns the analyst into an email channel users can write
    to and get answers from.
    """
    result = await external_platform_service.create_email_platform(
        db, organization, data, current_user,
    )
    try:
        await audit_service.log(
            db=db,
            organization_id=organization.id,
            action="integration.created",
            user_id=current_user.id,
            resource_type="integration",
            resource_id=result.id if hasattr(result, "id") else None,
            details={"type": "email", "inbound": bool(data.imap_host)},
            request=request,
        )
    except Exception:
        pass
    return result

@router.post("/settings/integrations/teams", response_model=ExternalPlatformSchema)
@requires_permission('manage_settings')
async def create_teams_integration(
    data: TeamsConfig,
    request: Request,
    current_user: User = Depends(current_user),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new Teams integration"""
    result = await external_platform_service.create_teams_platform(
        db, organization, data.app_id, data.client_secret, data.tenant_id, current_user,
        auto_link_by_email=data.auto_link_by_email,
    )
    try:
        await audit_service.log(
            db=db,
            organization_id=organization.id,
            action="integration.created",
            user_id=current_user.id,
            resource_type="integration",
            resource_id=result.id if hasattr(result, "id") else None,
            details={"type": "teams"},
            request=request,
        )
    except Exception:
        pass
    return result