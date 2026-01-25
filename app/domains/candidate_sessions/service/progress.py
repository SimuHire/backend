from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.progress import (
    compute_current_task,
    summarize_progress,
)


async def load_tasks(db: AsyncSession, simulation_id: int) -> list[Task]:
    tasks = await cs_repo.tasks_for_simulation(db, simulation_id)
    if not tasks:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulation has no tasks",
        )
    return tasks


async def completed_task_ids(db: AsyncSession, candidate_session_id: int) -> set[int]:
    return await cs_repo.completed_task_ids(db, candidate_session_id)


async def progress_snapshot(
    db: AsyncSession,
    candidate_session: CandidateSession,
    *,
    tasks: list[Task] | None = None,
) -> tuple[list[Task], set[int], Task | None, int, int, bool]:
    task_list = tasks or await load_tasks(db, candidate_session.simulation_id)
    completed_ids = await completed_task_ids(db, candidate_session.id)
    current = compute_current_task(task_list, completed_ids)
    completed, total, is_complete = summarize_progress(len(task_list), completed_ids)
    return task_list, completed_ids, current, completed, total, is_complete
