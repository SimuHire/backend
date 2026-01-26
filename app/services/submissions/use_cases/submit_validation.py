from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service
from app.domains.submissions import service_candidate as submission_service


async def validate_submission_flow(
    db: AsyncSession,
    candidate_session: CandidateSession,
    task_id: int,
    payload,
):
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)
    await submission_service.ensure_not_duplicate(db, candidate_session.id, task_id)
    _, _, current_task, *_ = await cs_service.progress_snapshot(db, candidate_session)
    submission_service.ensure_in_order(current_task, task_id)
    submission_service.validate_submission_payload(task, payload)
    return task
