from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_maker, get_session
from app.models.user import User
from app.security import auth0

bearer_scheme = HTTPBearer(auto_error=False)


def _env_name() -> str:
    return str(getattr(settings, "ENV", os.getenv("ENV", "local"))).lower()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Return the current user, creating them on first login.

    LOCAL DEV AUTH BYPASS (safe):
      - Only active when DEV_AUTH_BYPASS=1
      - AND request includes header: x-dev-user-email
      - AND ENV=local
      - AND request comes from 127.0.0.1 / ::1
    """
    dev_email = (request.headers.get("x-dev-user-email") or "").strip().lower()
    if dev_email and settings.ENV in ("local", "test"):
        result = await db.execute(select(User).where(User.email == dev_email))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Dev user not found: {dev_email}",
            )
        return user

    # -------------------------
    # LOCAL DEV AUTH BYPASS
    # -------------------------
    if os.getenv("DEV_AUTH_BYPASS") == "1" and dev_email:
        if _env_name() != "local":
            raise RuntimeError(
                "DEV_AUTH_BYPASS must never be enabled outside ENV=local"
            )

        client_host = getattr(request.client, "host", "")
        if client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="DEV_AUTH_BYPASS only allowed from localhost",
            )

        email = dev_email.strip()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Empty x-dev-user-email header",
            )

        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if user is None:
                # Safer: don't auto-create in bypass mode; seed the user so company_id is valid.
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        f"Dev user not found: {email}. Seed this user in the DB first "
                        "so it has a valid company_id."
                    ),
                )

        return user

    # -------------------------
    # NORMAL AUTH0 JWT FLOW
    # -------------------------
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials

    try:
        claims = auth0.decode_auth0_token(token)
    except auth0.Auth0Error as exc:
        raise exc

    email_value = claims.get("email") or claims.get("https://simuhire.com/email")
    if not isinstance(email_value, str) or not email_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email claim missing",
        )
    email = email_value

    name_value = claims.get("name") or claims.get("https://simuhire.com/name")
    if isinstance(name_value, str) and name_value.strip():
        name = name_value.strip()
    else:
        name = email.split("@")[0]

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                name=name,
                email=email,
                role="recruiter",
                password_hash="",
            )
            session.add(user)

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one()
            else:
                await session.refresh(user)

    return user
