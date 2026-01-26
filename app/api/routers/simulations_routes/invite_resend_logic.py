from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.simulations_routes.rate_limits import enforce_invite_resend_limit
from app.core.auth.roles import ensure_recruiter_or_none
from app.domains import CandidateSession
from app.domains.notifications import service as notification_service
from app.domains.simulations import service as sim_service
from app.services.email import EmailService


async def resend_invite(
    *,
    simulation_id: int,
    candidate_session_id: int,
    request: Request,
    db: AsyncSession,
    user,
    email_service: EmailService,
) -> CandidateSession:
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
    return cs


__all__ = ["resend_invite"]
