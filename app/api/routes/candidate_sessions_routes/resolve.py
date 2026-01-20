from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate_sessions import service as cs_service
from app.domains.candidate_sessions.schemas import CandidateSessionResolveResponse
from app.api.routes.candidate_sessions_routes.rate_limits import rate_limit_claim
from app.api.routes.candidate_sessions_routes.responses import (
    render_claim_response,
    utcnow,
)
from app.infra.db import get_session
from app.infra.security.candidate_access import require_candidate_principal
from app.infra.security.principal import Principal

router = APIRouter()


@router.get("/session/{token}", response_model=CandidateSessionResolveResponse)
async def resolve_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateSessionResolveResponse:
    """Claim an invite token for the authenticated candidate."""
    rate_limit_claim(request, token)
    cs = await cs_service.claim_invite_with_principal(db, token, principal, now=utcnow())
    return render_claim_response(cs)


@router.post(
    "/session/{token}/claim",
    response_model=CandidateSessionResolveResponse,
    status_code=status.HTTP_200_OK,
)
async def claim_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_candidate_principal)],
) -> CandidateSessionResolveResponse:
    """Idempotent claim endpoint for authenticated candidates (no email body required)."""
    rate_limit_claim(request, token)
    cs = await cs_service.claim_invite_with_principal(db, token, principal, now=utcnow())
    return render_claim_response(cs)
