from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.github_native import get_github_client
from app.api.dependencies.notifications import get_email_service
from app.api.routers.simulations_routes.invite_create_logic import (
    create_invite_response,
)
from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter_or_none
from app.core.db import get_session
from app.domains.candidate_sessions.schemas import (
    CandidateInviteErrorResponse,
    CandidateInviteRequest,
    CandidateInviteResponse,
)
from app.integrations.github import GithubClient
from app.services.email import EmailService

router = APIRouter()


@router.post(
    "/{simulation_id}/invite",
    response_model=CandidateInviteResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_409_CONFLICT: {"model": CandidateInviteErrorResponse}},
)
async def create_candidate_invite(
    simulation_id: int,
    payload: CandidateInviteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
):
    """Create a candidate_session invite token for a simulation (recruiter-only)."""
    ensure_recruiter_or_none(user)
    return await create_invite_response(
        db,
        simulation_id=simulation_id,
        payload=payload,
        user_id=user.id,
        request=request,
        email_service=email_service,
        github_client=github_client,
    )
