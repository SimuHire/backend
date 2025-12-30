from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains import CandidateSession, Submission, Task


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
