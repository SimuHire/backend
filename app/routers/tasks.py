from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy import distinct, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.candidate_session import CandidateSession
from app.models.submission import Submission
from app.models.task import Task
from app.schemas.submission import (
    ProgressSummary,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)
from app.utils.progress import compute_current_task, summarize_progress

router = APIRouter()


TEXT_TASK_TYPES = {"design", "documentation", "handoff"}
CODE_TASK_TYPES = {"code", "debug"}


async def _load_candidate_session_or_404(
    db: AsyncSession,
    candidate_session_id: int,
    token: str,
) -> CandidateSession:
    stmt = select(CandidateSession).where(CandidateSession.id == candidate_session_id)
    res = await db.execute(stmt)
    cs = res.scalar_one_or_none()

    if cs is None:
        raise HTTPException(status_code=404, detail="Candidate session not found")
    if cs.token != token:
        raise HTTPException(status_code=404, detail="Candidate session not found")

    now = datetime.now(UTC)
    expires_at = cs.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at is not None and expires_at < now:
        raise HTTPException(status_code=410, detail="Invite token expired")

    return cs


async def _compute_current_task(db: AsyncSession, cs: CandidateSession) -> Task | None:
    tasks_stmt = (
        select(Task)
        .where(Task.simulation_id == cs.simulation_id)
        .order_by(Task.day_index.asc())
    )
    tasks_res = await db.execute(tasks_stmt)
    tasks = list(tasks_res.scalars().all())

    if not tasks:
        raise HTTPException(status_code=500, detail="Simulation has no tasks")

    completed_stmt = select(distinct(Submission.task_id)).where(
        Submission.candidate_session_id == cs.id
    )
    completed_res = await db.execute(completed_stmt)
    completed_task_ids = set(completed_res.scalars().all())

    return compute_current_task(tasks, completed_task_ids)


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

    task_stmt = select(Task).where(Task.id == task_id)
    task_res = await db.execute(task_stmt)
    task = task_res.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.simulation_id != cs.simulation_id:
        raise HTTPException(status_code=404, detail="Task not found")

    dup_stmt = select(Submission.id).where(
        Submission.candidate_session_id == cs.id,
        Submission.task_id == task_id,
    )
    dup_res = await db.execute(dup_stmt)
    if dup_res.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Task already submitted")

    current_task = await _compute_current_task(db, cs)
    if current_task is None:
        raise HTTPException(status_code=409, detail="Simulation already completed")
    if current_task.id != task_id:
        raise HTTPException(status_code=400, detail="Task out of order")

    task_type = (task.type or "").lower()

    if task_type in TEXT_TASK_TYPES:
        if not payload.contentText or not payload.contentText.strip():
            raise HTTPException(status_code=400, detail="contentText is required")
    elif task_type in CODE_TASK_TYPES:
        has_code_blob = bool(payload.codeBlob and payload.codeBlob.strip())
        has_files = bool(payload.files)
        if not (has_code_blob or has_files):
            raise HTTPException(status_code=400, detail="codeBlob or files is required")
    else:
        raise HTTPException(status_code=500, detail="Unknown task type")

    now = datetime.now(UTC)
    sub = Submission(
        candidate_session_id=cs.id,
        task_id=task.id,
        submitted_at=now,
        content_text=payload.contentText,
        code_blob=payload.codeBlob,
        code_repo_path=None,
    )

    db.add(sub)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Task already submitted") from exc
    await db.refresh(sub)

    tasks_stmt = select(Task.id).where(Task.simulation_id == cs.simulation_id)
    tasks_res = await db.execute(tasks_stmt)
    total = len(list(tasks_res.scalars().all()))

    completed_stmt = select(distinct(Submission.task_id)).where(
        Submission.candidate_session_id == cs.id
    )
    completed_res = await db.execute(completed_stmt)
    completed_task_ids = set(completed_res.scalars().all())
    completed, total, is_complete = summarize_progress(total, completed_task_ids)

    if is_complete and cs.status != "completed":
        cs.status = "completed"
        if cs.completed_at is None:
            cs.completed_at = now
        await db.commit()
        await db.refresh(cs)

    return SubmissionCreateResponse(
        submissionId=sub.id,
        taskId=task.id,
        candidateSessionId=cs.id,
        submittedAt=sub.submitted_at,
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )
