from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.domains import CandidateSession, FitProfile
from app.domains.simulations import repository as sim_repo


async def list_simulations(db: AsyncSession, user_id: int):
    """List simulations with candidate counts for a recruiter."""
    return await sim_repo.list_with_candidate_counts(db, user_id)


async def list_candidates_with_profile(
    db: AsyncSession, simulation_id: int
) -> list[tuple[CandidateSession, int | None]]:
    stmt = (
        select(CandidateSession, FitProfile.id)
        .options(
            load_only(
                CandidateSession.id,
                CandidateSession.invite_email,
                CandidateSession.candidate_name,
                CandidateSession.status,
                CandidateSession.started_at,
                CandidateSession.completed_at,
                CandidateSession.invite_email_status,
                CandidateSession.invite_email_sent_at,
                CandidateSession.invite_email_error,
            )
        )
        .outerjoin(
            FitProfile,
            FitProfile.candidate_session_id == CandidateSession.id,
        )
        .where(CandidateSession.simulation_id == simulation_id)
        .order_by(CandidateSession.id.desc())
    )
    return (await db.execute(stmt)).all()
