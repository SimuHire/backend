from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate_sessions.schemas import CandidateSessionListItem
from app.domains.simulations import service as sim_service
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.roles import ensure_recruiter_or_none

router = APIRouter()


@router.get(
    "/{simulation_id}/candidates",
    response_model=list[CandidateSessionListItem],
    status_code=status.HTTP_200_OK,
)
async def list_simulation_candidates(
    simulation_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """List candidate sessions for a simulation (recruiter-only)."""
    ensure_recruiter_or_none(user)
    await sim_service.require_owned_simulation(db, simulation_id, user.id)
    rows = await sim_service.list_candidates_with_profile(db, simulation_id)
    return [
        CandidateSessionListItem(
            candidateSessionId=cs.id,
            inviteEmail=cs.invite_email,
            candidateName=cs.candidate_name,
            status=cs.status,
            startedAt=cs.started_at,
            completedAt=cs.completed_at,
            hasFitProfile=(profile_id is not None),
            inviteEmailStatus=getattr(cs, "invite_email_status", None),
            inviteEmailSentAt=getattr(cs, "invite_email_sent_at", None),
            inviteEmailError=getattr(cs, "invite_email_error", None),
        )
        for cs, profile_id in rows
    ]
