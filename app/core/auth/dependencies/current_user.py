from __future__ import annotations

import sys
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.principal import bearer_scheme, get_principal
from app.core.db import get_session
from app.domains import User

from .dev_bypass import dev_bypass_user
from .users import user_from_principal


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Return the current user via dev bypass (local/test) or Auth0 JWT."""
    dep_module = sys.modules.get("app.core.auth.dependencies")
    dev_bypass = getattr(dep_module, "_dev_bypass_user", dev_bypass_user)
    user_loader = getattr(dep_module, "_user_from_principal", user_from_principal)

    dev_user = await dev_bypass(request, db)
    if dev_user:
        return dev_user

    principal = await get_principal(credentials, request)
    if "recruiter:access" not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )

    return await user_loader(principal, db)
