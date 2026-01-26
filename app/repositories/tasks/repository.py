from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Task


async def get_by_id(db: AsyncSession, task_id: int) -> Task | None:
    """Return task by id."""
    res = await db.execute(select(Task).where(Task.id == task_id))
    return res.scalar_one_or_none()
