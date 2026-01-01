from __future__ import annotations

import os
import sys
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import User
from app.infra.config import settings  # noqa: F401
from app.infra.db import async_session_maker, get_session
from app.infra.env import env_name as _env_name_base
from app.infra.security.principal import (
    Principal,
    bearer_scheme,
    get_principal,
)


def _current_user_module():
    """Return the loaded current_user module."""
    return sys.modules.get("app.infra.security.current_user")


def _env_name() -> str:
    """Env name with monkeypatch-friendly override via current_user._env_name."""
    current_user_mod = _current_user_module()
    override = getattr(current_user_mod, "_env_name", None)
    if callable(override) and override is not _env_name:
        return override()
    return _env_name_base()


async def _lookup_user(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _dev_bypass_user(request: Request, db: AsyncSession | None) -> User | None:
    """Allow local dev bypass when enabled and header present."""
    dev_email = (request.headers.get("x-dev-user-email") or "").strip().lower()
    if not dev_email:
        return None
    dev_bypass_env = os.getenv("DEV_AUTH_BYPASS") == "1"

    env_name = _env_name()
    if dev_bypass_env and env_name != "local":
        raise RuntimeError("DEV_AUTH_BYPASS must never be enabled outside ENV=local")

    if env_name not in {"local", "test"} and not dev_bypass_env:
        return None

    client_host = getattr(request.client, "host", "")
    if client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DEV_AUTH_BYPASS only allowed from localhost",
        )

    # Fallback to session maker if no session provided (legacy tests).
    if db is None:
        current_user_mod = _current_user_module()
        maker = getattr(current_user_mod, "async_session_maker", async_session_maker)
        async with maker() as session:
            return await _dev_bypass_user(request, session)

    user = await _lookup_user(db, dev_email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Dev user not found: {dev_email}",
        )
    return user


async def _user_from_principal(principal: Principal, db: AsyncSession | None) -> User:
    """Find or create a recruiter user from the authenticated principal."""
    # Prefer injected db; fall back to session maker for backward-compat.
    if db is None:
        current_user_mod = _current_user_module()
        maker = getattr(current_user_mod, "async_session_maker", async_session_maker)
        async with maker() as session:
            return await _user_from_principal(principal, session)

    user = await _lookup_user(db, principal.email)
    if user is None:
        user = User(
            name=principal.name or principal.email.split("@")[0],
            email=principal.email,
            role="recruiter",
            password_hash="",
        )
        db.add(user)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            user = await _lookup_user(db, principal.email)
        else:
            await db.refresh(user)

    return user


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Return the current user via dev bypass (local/test) or Auth0 JWT."""
    dev_user = await _dev_bypass_user(request, db)
    if dev_user:
        return dev_user

    principal = await get_principal(credentials)
    if "recruiter:access" not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )

    return await _user_from_principal(principal, db)
