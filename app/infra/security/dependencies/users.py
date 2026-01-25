from __future__ import annotations

import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import User
from app.infra.db import async_session_maker
from app.infra.security.principal import Principal

from .db import lookup_user as lookup_user_default
from .modules import current_user_module


async def user_from_principal(principal: Principal, db: AsyncSession | None) -> User:
    # Prefer injected db; fall back to session maker for backward-compat.
    if db is None:
        current_user_mod = current_user_module()
        maker = getattr(current_user_mod, "async_session_maker", async_session_maker)
        async with maker() as session:
            return await user_from_principal(principal, session)

    dep_module = sys.modules.get("app.infra.security.dependencies")
    lookup_user = getattr(dep_module, "_lookup_user", lookup_user_default)
    user = await lookup_user(db, principal.email)
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
            user = await lookup_user(db, principal.email)
        else:
            await db.refresh(user)

    return user
