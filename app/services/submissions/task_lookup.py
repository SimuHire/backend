from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Task


async def load_task_or_404(db: AsyncSession, task_id: int) -> Task:
    """Fetch a task by id or raise 404."""
    from app.domains.submissions import service_candidate as _svc

    task = await _svc.tasks_repo.get_by_id(db, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task
