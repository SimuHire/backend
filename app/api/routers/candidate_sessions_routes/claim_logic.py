from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.candidate_sessions_routes.rate_limits import rate_limit_claim
from app.api.routers.candidate_sessions_routes.time_utils import utcnow
from app.core.auth.principal import Principal
from app.domains.candidate_sessions import service as cs_service


async def claim_token(
    token: str, request: Request, principal: Principal, db: AsyncSession
):
    rate_limit_claim(request, token)
    return await cs_service.claim_invite_with_principal(
        db, token, principal, now=utcnow()
    )


__all__ = ["claim_token"]
