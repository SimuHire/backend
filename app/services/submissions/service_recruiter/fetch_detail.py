from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Simulation, Submission, Task


async def fetch_detail(
    db: AsyncSession, submission_id: int, recruiter_id: int
) -> tuple[Submission, Task, CandidateSession, Simulation]:
    """Load submission with task/session/simulation; enforce ownership."""
    stmt = (
        select(Submission, Task, CandidateSession, Simulation)
        .join(Task, Task.id == Submission.task_id)
        .join(CandidateSession, CandidateSession.id == Submission.candidate_session_id)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(Submission.id == submission_id)
        .where(Simulation.created_by == recruiter_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return row
