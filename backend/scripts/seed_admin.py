"""
Seed the first super-admin from environment variables.
======================================================

Bootstraps the very first owner/admin user of a fresh deploy purely from env,
so nobody has to hit ``POST /api/auth/register`` by hand (the UI sign-up link
was removed). This is the supported first-run bootstrap path.

Reads:
    DASH_ADMIN_EMAIL       (required — skip if missing)
    DASH_ADMIN_PASSWORD    (required — skip if missing)
    DASH_ADMIN_NAME        (optional, default "Admin")

Behaviour:
    * If email or password is missing  -> print a skip message, exit 0.
    * If a user with that email exists  -> "admin already exists", exit 0.
    * Otherwise create the user THROUGH the user manager so the existing
      ``on_after_register`` hook fires — that hook is what creates the org and
      makes this user its owner. Then flip is_active/is_verified/is_superuser
      so the env admin is a real global admin regardless of what UserCreate
      accepts.

Design notes:
    * Idempotent — safe to run on every container boot.
    * Fail-soft — ANY error is caught, logged, and we exit 0. A failed seed
      must NEVER crash the container / block uvicorn from starting.
    * Run ONCE in start.sh BEFORE uvicorn forks its workers (not in a FastAPI
      startup_event — that runs per-worker and would race N workers).

Run (inside the backend dir, the container venv has the deps):
    cd /app/backend && python scripts/seed_admin.py
"""

import asyncio
import os
import sys

# Ensure the backend package root is importable when run as a standalone script
# from /app/backend (matches how other scripts here resolve imports).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PREFIX = "[seed_admin]"


def _log(msg: str) -> None:
    print(f"{PREFIX} {msg}", flush=True)


async def _seed_create(email: str, password: str, name: str) -> None:
    """Create the admin through the user manager and elevate it."""
    from sqlalchemy import select, func
    from app.dependencies import async_session_maker, get_user_db
    from app.core.auth import get_user_manager
    from app.schemas.user_schema import UserCreate
    from app.models.user import User

    # Open ONE async session and feed it through the user-db / user-manager deps.
    async with async_session_maker() as session:
        # get_user_db yields a SQLAlchemyUserDatabase bound to this session.
        user_db_gen = get_user_db(session=session)
        user_db = await user_db_gen.__anext__()
        try:
            manager_gen = get_user_manager(user_db=user_db)
            manager = await manager_gen.__anext__()
            try:
                # safe=False so we may set privileged flags; on_after_register
                # runs inside .create() and creates the org + owner membership.
                user = await manager.create(
                    UserCreate(email=email, password=password, name=name),
                    safe=False,
                )
                # Capture id as a plain value before any further commit/expiry.
                user_id = str(user.id)
                _log(f"created admin user {email} (id={user_id}); org + owner provisioned.")
            finally:
                await _aclose(manager_gen)
        finally:
            await _aclose(user_db_gen)

    # 3) Elevate to a real global admin in a fresh session (avoid expired ORM).
    async with async_session_maker() as session:
        row = (
            await session.execute(
                select(User).where(func.lower(User.email) == email.lower())
            )
        ).scalar_one_or_none()
        if row is None:
            _log("warning: user vanished after creation — cannot elevate.")
            return
        row.is_active = True
        row.is_verified = True
        row.is_superuser = True
        await session.commit()
        _log(f"elevated {email} -> is_active/is_verified/is_superuser = True.")


async def _aclose(gen) -> None:
    """Best-effort close of an async generator dependency."""
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass
    except Exception:
        pass


async def main_async() -> None:
    email = (os.environ.get("DASH_ADMIN_EMAIL") or "").strip()
    password = os.environ.get("DASH_ADMIN_PASSWORD") or ""
    name = (os.environ.get("DASH_ADMIN_NAME") or "Admin").strip() or "Admin"

    if not email or not password:
        _log("DASH_ADMIN_EMAIL / DASH_ADMIN_PASSWORD not set — skipping admin seed.")
        return

    # Register ORM models / app wiring (mirrors other in-container scripts).
    import main  # noqa: F401
    from sqlalchemy import select, func
    from app.dependencies import async_session_maker
    from app.models.user import User

    # Idempotency: bail early if this admin already exists.
    async with async_session_maker() as session:
        existing = (
            await session.execute(
                select(User).where(func.lower(User.email) == email.lower())
            )
        ).scalar_one_or_none()
        if existing is not None:
            _log(f"admin already exists ({email}) — skipping.")
            return

    await _seed_create(email, password, name)


def main_entry() -> None:
    try:
        asyncio.run(main_async())
    except Exception as exc:  # never block boot
        _log(f"ERROR (non-fatal, continuing boot): {exc!r}")
    # Always succeed so the container start script proceeds to uvicorn.
    sys.exit(0)


if __name__ == "__main__":
    main_entry()
