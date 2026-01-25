from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.candidate_sessions_routes.rate_limits import (
    CANDIDATE_INVITES_RATE_LIMIT,
)
from app.domains.candidate_sessions import service as cs_service
from app.domains.candidate_sessions.schemas import CandidateInviteListItem
from app.infra.db import get_session
from app.infra.security import rate_limit
from app.infra.security.candidate_access import require_candidate_principal
from app.infra.security.principal import Principal

router = APIRouter()


@router.get("/invites", response_model=list[CandidateInviteListItem])
async def list_candidate_invites(
    request: Request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[CandidateInviteListItem]:
    """List all invites for the authenticated candidate email."""
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_invites",
            rate_limit.hash_value(principal.sub),
            rate_limit.client_id(request),
        )
        rate_limit.limiter.allow(key, CANDIDATE_INVITES_RATE_LIMIT)
    return await cs_service.invite_list_for_principal(db, principal)
