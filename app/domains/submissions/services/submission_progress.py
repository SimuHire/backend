from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service


async def progress_after_submission(
    db: AsyncSession, candidate_session: CandidateSession, *, now: datetime
) -> tuple[int, int, bool]:
    """Recompute progress and update completion status if applicable."""
    (
        _,
        _completed_task_ids,
        _current,
        completed,
        total,
        is_complete,
    ) = await cs_service.progress_snapshot(db, candidate_session)

    if is_complete and candidate_session.status != "completed":
        candidate_session.status = "completed"
        if candidate_session.completed_at is None:
            candidate_session.completed_at = now
        await db.commit()
        await db.refresh(candidate_session)

    return completed, total, is_complete
