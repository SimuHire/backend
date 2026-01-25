from __future__ import annotations
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.notifications import get_email_service
from app.api.routes.simulations_routes.invite_render import render_invite_status
from app.api.routes.simulations_routes.rate_limits import enforce_invite_resend_limit
from app.domains import CandidateSession
from app.domains.notifications import service as notification_service
from app.domains.simulations import service as sim_service
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.roles import ensure_recruiter_or_none
from app.services.email import EmailService

router = APIRouter()

@router.post(
    "/{simulation_id}/candidates/{candidate_session_id}/invite/resend",
    status_code=status.HTTP_200_OK,
)
async def resend_candidate_invite(
    simulation_id: int,
    candidate_session_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
):
    ensure_recruiter_or_none(user)
    enforce_invite_resend_limit(request, user.id, candidate_session_id)

    sim = await sim_service.require_owned_simulation(db, simulation_id, user.id)
    cs: CandidateSession | None = await db.get(CandidateSession, candidate_session_id)
    if cs is None or cs.simulation_id != sim.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate session not found"
        )

    await notification_service.send_invite_email(
        db,
        candidate_session=cs,
        simulation=sim,
        invite_url=sim_service.invite_url(cs.token),
        email_service=email_service,
        now=None,
    )
    return render_invite_status(cs)
