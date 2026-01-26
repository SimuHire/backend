from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Submission, Task


async def tasks_for_simulation(db: AsyncSession, simulation_id: int) -> list[Task]:
    tasks_stmt = (
        select(Task)
        .where(Task.simulation_id == simulation_id)
        .order_by(Task.day_index.asc())
    )
    tasks_res = await db.execute(tasks_stmt)
    return list(tasks_res.scalars().all())


async def completed_task_ids(db: AsyncSession, candidate_session_id: int) -> set[int]:
    completed_stmt = select(distinct(Submission.task_id)).where(
        Submission.candidate_session_id == candidate_session_id
    )
    completed_res = await db.execute(completed_stmt)
    return set(completed_res.scalars().all())


__all__ = ["tasks_for_simulation", "completed_task_ids"]
