from __future__ import annotations

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains import CandidateSession, Submission, Task
from app.domains.simulations.simulation import Simulation


async def get_by_token(
    db: AsyncSession, token: str, *, with_simulation: bool = False
) -> CandidateSession | None:
    """Return candidate session by token, optionally eager-loading simulation."""
    stmt = select(CandidateSession).where(CandidateSession.token == token)
    if with_simulation:
        stmt = stmt.options(selectinload(CandidateSession.simulation))
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_by_id(db: AsyncSession, session_id: int) -> CandidateSession | None:
    """Return candidate session by id."""
    res = await db.execute(
        select(CandidateSession).where(CandidateSession.id == session_id)
    )
    return res.scalar_one_or_none()


async def get_by_access_token_hash(
    db: AsyncSession, token_hash: str
) -> CandidateSession | None:
    """Lookup a candidate session by access token hash."""
    res = await db.execute(
        select(CandidateSession).where(
            CandidateSession.candidate_access_token_hash == token_hash
        )
    )
    return res.scalar_one_or_none()


async def tasks_for_simulation(db: AsyncSession, simulation_id: int) -> list[Task]:
    """Return tasks ordered by day_index for a simulation."""
    tasks_stmt = (
        select(Task)
        .where(Task.simulation_id == simulation_id)
        .order_by(Task.day_index.asc())
    )
    tasks_res = await db.execute(tasks_stmt)
    return list(tasks_res.scalars().all())


async def completed_task_ids(db: AsyncSession, candidate_session_id: int) -> set[int]:
    """Return distinct task ids already submitted for a candidate session."""
    completed_stmt = select(distinct(Submission.task_id)).where(
        Submission.candidate_session_id == candidate_session_id
    )
    completed_res = await db.execute(completed_stmt)
    return set(completed_res.scalars().all())


async def list_for_email(db: AsyncSession, email: str) -> list[CandidateSession]:
    """Return candidate sessions for a given invite email (case-insensitive)."""
    stmt = (
        select(CandidateSession)
        .where(func.lower(CandidateSession.invite_email) == func.lower(email))
        .options(
            selectinload(CandidateSession.simulation).selectinload(Simulation.company)
        )
    )
    res = await db.execute(stmt)
    return list(res.scalars().unique().all())


async def last_submission_at(
    db: AsyncSession, candidate_session_id: int
) -> datetime | None:
    """Return the most recent submission timestamp for a candidate session."""
    stmt = select(func.max(Submission.submitted_at)).where(
        Submission.candidate_session_id == candidate_session_id
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()
