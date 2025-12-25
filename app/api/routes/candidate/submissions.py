from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain import CandidateSession, Task
from app.domain.candidate_sessions import service as cs_service
from app.domain.submissions import service_candidate as submission_service
from app.domain.submissions.schemas import (
    ProgressSummary,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)

router = APIRouter()


TEXT_TASK_TYPES = {"design", "documentation", "handoff"}
CODE_TASK_TYPES = {"code", "debug"}


async def _load_candidate_session_or_404(
    db: AsyncSession,
    candidate_session_id: int,
    token: str,
) -> CandidateSession:
    return await cs_service.fetch_by_id_and_token(
        db, candidate_session_id, token, now=datetime.now(UTC)
    )


async def _compute_current_task(db: AsyncSession, cs: CandidateSession) -> Task | None:
    tasks, completed_task_ids, current, *_ = await cs_service.progress_snapshot(db, cs)
    return current


@router.post(
    "/{task_id}/submit",
    response_model=SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: SubmissionCreateRequest,
    x_candidate_token: Annotated[str, Header(..., alias="x-candidate-token")],
    x_candidate_session_id: Annotated[int, Header(..., alias="x-candidate-session-id")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> SubmissionCreateResponse:
    """Submit a task for a candidate session. Enforces ordering and idempotency."""
    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )

    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    await submission_service.ensure_not_duplicate(db, cs.id, task_id)

    current_task = await _compute_current_task(db, cs)
    submission_service.ensure_in_order(current_task, task_id)
    submission_service.validate_payload(task, payload)

    now = datetime.now(UTC)
    sub = await submission_service.create_submission(db, cs, task, payload, now=now)

    completed, total, is_complete = await submission_service.progress_after_submission(
        db, cs, now=now
    )

    return SubmissionCreateResponse(
        submissionId=sub.id,
        taskId=task.id,
        candidateSessionId=cs.id,
        submittedAt=sub.submitted_at,
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )
