from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Simulation, Submission


async def find_duplicate(
    db: AsyncSession, candidate_session_id: int, task_id: int
) -> bool:
    """Return True if a submission already exists for candidate/task."""
    dup_stmt = select(Submission.id).where(
        Submission.candidate_session_id == candidate_session_id,
        Submission.task_id == task_id,
    )
    dup_res = await db.execute(dup_stmt)
    return dup_res.scalar_one_or_none() is not None


async def simulation_template(db: AsyncSession, simulation_id: int) -> str | None:
    """Return a stable scenario key for a simulation."""
    stmt = select(
        Simulation.scenario_template,
        Simulation.focus,
    ).where(Simulation.id == simulation_id)
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        return None
    scenario_template, focus = row
    return scenario_template or focus
