"""OAuth 2.0 device-code sign-in for the Power BI user connector (MFA-safe).

ROPC (email + password) dies the moment an account has MFA enabled
(``AADSTS50076``/``50079``) or the tenant blocks legacy auth (``AADSTS7000218``).
The device-code flow is the self-serve alternative: the app shows a short
``user_code`` + a verification URL; the user approves on any device (MFA/2FA
happens there natively) and the app polls until a token — plus a refresh token —
comes back.

Two pure functions (mirroring ``powerbi_tenant_discovery.py`` — no FastAPI, no DB):
``start_device_code`` kicks off the flow; ``poll_device_code`` does ONE poll (the
caller loops). ``offline_access`` is in the scope so we get a refresh token, which
we persist (encrypted) so future scans don't need a re-login.

Never raises; network/HTTP failures come back as ``{"ok": False, ...}`` /
``{"status": "error", ...}``. Never logs tokens.
"""
from __future__ import annotations

import requests

_PUBLIC_CLIENT = "1950a258-227b-4e31-a9cf-717495945fc2"  # MS FOCI public client (no secret)
_DEVICECODE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
# offline_access = REQUIRED to receive a refresh_token back.
_SCOPE = "https://analysis.windows.net/powerbi/api/.default offline_access"

# Per-connector device-code scopes. All use the SAME FOCI public client above —
# a refresh_token issued for one family member (e.g. Power BI) can be redeemed for
# a token to another (Fabric SQL / Graph) via the refresh-grant helper below.
# offline_access on every scope so we always get a refresh_token back.
SCOPE_POWERBI = _SCOPE
SCOPE_FABRIC = "https://database.windows.net/.default offline_access"
SCOPE_GRAPH = "https://graph.microsoft.com/.default offline_access"
# Fabric SQL endpoint token audience (used when minting an access token to feed
# the ODBC driver via attrs_before={1256: ...}).
FABRIC_TOKEN_SCOPE = "https://database.windows.net/.default"


def _err_detail(resp: requests.Response) -> str:
    try:
        j = resp.json()
        return f"{j.get('error')}: {j.get('error_description', '')[:300]}"
    except Exception:  # noqa: BLE001
        return resp.text[:300]


def start_device_code(tenant_id: str, client_id: str | None = None, scope: str | None = None) -> dict:
    """Begin the device-code flow. Returns the user_code + verification URL to show.

    ``tenant_id`` = a concrete tenant GUID or the multi-tenant word ``organizations``.
    ``scope`` defaults to the Power BI scope; pass ``SCOPE_FABRIC``/``SCOPE_GRAPH``
    for a Fabric SQL / Graph token (same FOCI public client, different resource).
    """
    if not tenant_id:
        return {"ok": False, "error": "tenant_id is required"}
    try:
        resp = requests.post(
            _DEVICECODE_URL.format(tenant=tenant_id),
            data={"client_id": client_id or _PUBLIC_CLIENT, "scope": scope or _SCOPE},
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if resp.status_code >= 300:
        return {"ok": False, "error": _err_detail(resp)}
    j = resp.json() or {}
    return {
        "ok": True,
        "device_code": j.get("device_code"),
        "user_code": j.get("user_code"),
        "verification_uri": j.get("verification_uri") or j.get("verification_url"),
        "expires_in": j.get("expires_in"),
        "interval": j.get("interval") or 5,
        "message": j.get("message"),
    }


def poll_device_code(tenant_id: str, device_code: str, client_id: str | None = None) -> dict:
    """Poll ONCE for the device-code token. Caller loops on ``status == 'pending'``.

    Returns one of:
      ``{"status": "success", "access_token", "refresh_token", "expires_in"}``
      ``{"status": "pending"}``            (optionally ``"slow_down": True``)
      ``{"status": "error", "error": str}``
    """
    if not (tenant_id and device_code):
        return {"status": "error", "error": "tenant_id and device_code are required"}
    try:
        resp = requests.post(
            _TOKEN_URL.format(tenant=tenant_id),
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id or _PUBLIC_CLIENT,
                "device_code": device_code,
            },
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}

    if resp.status_code < 300:
        j = resp.json() or {}
        return {
            "status": "success",
            "access_token": j.get("access_token"),
            "refresh_token": j.get("refresh_token"),
            "expires_in": j.get("expires_in"),
        }

    # HTTP 400 carries the flow state in `error`.
    err = ""
    try:
        err = (resp.json() or {}).get("error", "")
    except Exception:  # noqa: BLE001
        err = ""
    if err == "authorization_pending":
        return {"status": "pending"}
    if err == "slow_down":
        return {"status": "pending", "slow_down": True}
    return {"status": "error", "error": _err_detail(resp)}


def refresh_to_access_token(
    tenant_id: str,
    refresh_token: str,
    scope: str,
    client_id: str | None = None,
) -> dict:
    """Redeem a stored refresh_token for a fresh access_token at ``scope``.

    Because the device-code flow uses a FOCI public client, a refresh_token
    obtained for one Microsoft resource can be exchanged for a token to another
    (e.g. a Power BI refresh_token → a Fabric ``database.windows.net`` SQL token).
    Azure may rotate the refresh_token — the new one (when present) is returned so
    the caller can persist it. Never raises; never logs the token.

    Returns:
      ``{"ok": True, "access_token", "refresh_token"|None, "expires_in"}`` or
      ``{"ok": False, "error": str}``.
    """
    if not (tenant_id and refresh_token and scope):
        return {"ok": False, "error": "tenant_id, refresh_token and scope are required"}
    try:
        resp = requests.post(
            _TOKEN_URL.format(tenant=tenant_id),
            data={
                "grant_type": "refresh_token",
                "client_id": client_id or _PUBLIC_CLIENT,
                "refresh_token": refresh_token,
                "scope": scope,
            },
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if resp.status_code >= 300:
        return {"ok": False, "error": _err_detail(resp)}
    j = resp.json() or {}
    return {
        "ok": True,
        "access_token": j.get("access_token"),
        # Azure returns a rotated refresh_token on some tenants; keep the old one if absent.
        "refresh_token": j.get("refresh_token"),
        "expires_in": j.get("expires_in"),
    }
