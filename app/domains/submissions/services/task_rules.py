from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.domains.submissions import repository as submissions_repo
from app.domains.submissions.exceptions import (
    SimulationComplete,
    SubmissionConflict,
    SubmissionOrderError,
)


def ensure_task_belongs(task: Task, candidate_session: CandidateSession) -> None:
    """Ensure the task is part of the candidate's simulation."""
    if task.simulation_id != candidate_session.simulation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )


async def ensure_not_duplicate(
    db: AsyncSession, candidate_session_id: int, task_id: int
) -> None:
    """Guard against duplicate submissions for a task."""
    if await submissions_repo.find_duplicate(db, candidate_session_id, task_id):
        raise SubmissionConflict()


def ensure_in_order(current_task: Task | None, target_task_id: int) -> None:
    """Verify the submission is for the current task in sequence."""
    if current_task is None:
        raise SimulationComplete()
    if current_task.id != target_task_id:
        raise SubmissionOrderError()
