import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.settings.config import settings
from app.dependencies import get_current_locale, get_current_organization, _locale_from_org
from app.models.organization import Organization

router = APIRouter()

@router.get("/settings", tags=["settings"])
async def get_frontend_settings():
    """Get frontend configuration settings"""
    is_testing = os.getenv("TESTING", "").lower() == "true"

    # Hybrid product version (VERSION_HYBRID) — what the UI brands itself as.
    # Distinct from settings.PROJECT_VERSION (the upstream dash base version).
    try:
        from app.services.changelog import current_version
        hybrid_version = current_version()
    except Exception:
        hybrid_version = None

    # SSO: prefer DB config (live, no restart) over file config
    try:
        from app.services.organization_settings_service import (
            get_effective_google_oauth,
            get_effective_oidc_providers,
            get_effective_auth_mode,
            get_effective_signup_enabled,
            get_effective_ldap_enabled,
            get_effective_ldap_logo,
        )
        eff_google = await get_effective_google_oauth()
        eff_oidc = await get_effective_oidc_providers()
        eff_mode = await get_effective_auth_mode()
        google_enabled = eff_google.get("enabled", False)
        google_logo = eff_google.get("logo", "")
        oidc_list = [{"name": p.name, "enabled": p.enabled, "logo": getattr(p, "logo", "")} for p in eff_oidc]
        auth_mode = eff_mode
        signup_enabled = await get_effective_signup_enabled()
        ldap_enabled = await get_effective_ldap_enabled()
        ldap_logo = await get_effective_ldap_logo()
    except Exception:
        google_enabled = settings.dash_config.google_oauth.enabled
        google_logo = ""
        oidc_list = [
            {"name": p.name, "enabled": p.enabled, "logo": getattr(p, "logo", "")}
            for p in getattr(settings.dash_config, "oidc_providers", []) or []
        ]
        auth_mode = getattr(settings.dash_config, 'auth').mode if hasattr(settings.dash_config, 'auth') else 'hybrid'
        signup_enabled = bool(settings.dash_config.features.allow_uninvited_signups)
        _file_ldap = getattr(settings.dash_config, "ldap", None)
        ldap_enabled = bool(getattr(_file_ldap, "enabled", False)) if _file_ldap else False
        ldap_logo = ""

    return JSONResponse({
        "google_oauth": {
            "enabled": google_enabled,
            "logo": google_logo,
        },
        "auth": {
            "mode": auth_mode,
        },
        "oidc_providers": oidc_list,
        "ldap_enabled": ldap_enabled,
        "ldap_logo": ldap_logo,
        "signup_enabled": signup_enabled,
        "features": {
            "allow_uninvited_signups": settings.dash_config.features.allow_uninvited_signups,
            "allow_multiple_organizations": settings.dash_config.features.allow_multiple_organizations,
            "verify_emails": settings.dash_config.features.verify_emails,
        },
        "deployment": {
            "type": settings.dash_config.deployment.type if hasattr(settings.dash_config, 'deployment') else "development",
        },
        "base_url": settings.dash_config.base_url,
        "intercom": {
            "enabled": settings.dash_config.intercom.enabled and not is_testing,
        },
        "telemetry": {
            "enabled": settings.dash_config.telemetry.enabled and not is_testing,
        },
        "smtp_enabled": settings.dash_config.smtp_settings is not None,
        "version": settings.PROJECT_VERSION,
        "hybrid_version": hybrid_version,
        "environment": settings.ENVIRONMENT,
        "i18n": {
            "default_locale": settings.dash_config.i18n.default_locale,
            "enabled_locales": settings.dash_config.i18n.enabled_locales,
            "fallback_locale": settings.dash_config.i18n.fallback_locale,
        },
    })


@router.get("/config/i18n", tags=["settings"])
async def get_i18n_config(request: Request):
    """Public i18n config: available locales and effective locale for this request.

    When an org header is present and valid, returns the org-overridden locale;
    otherwise returns the system default. X-Locale header (if in enabled list)
    takes highest priority.
    """
    i18n = settings.dash_config.i18n
    current_locale = await get_current_locale(request)

    org_locale = None
    org_id = request.headers.get("X-Organization-Id")
    if org_id:
        try:
            from app.dependencies import get_async_session
            from sqlalchemy import select
            async for db in get_async_session():
                org = (await db.execute(select(Organization).filter(Organization.id == org_id))).scalar_one_or_none()
                if org is not None:
                    org_locale = _locale_from_org(org)
                break
        except Exception:
            org_locale = None

    override = request.headers.get("X-Locale")
    if override and override in i18n.enabled_locales:
        current_locale = override
    elif org_locale:
        current_locale = org_locale

    return JSONResponse({
        "default_locale": i18n.default_locale,
        "enabled_locales": i18n.enabled_locales,
        "fallback_locale": i18n.fallback_locale,
        "current_locale": current_locale,
        "org_locale": org_locale,
    })
