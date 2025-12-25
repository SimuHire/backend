from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models.candidate_session import CandidateSession
from app.models.submission import Submission
from app.models.task import Task
from app.schemas.candidate_session import (
    CandidateSessionResolveResponse,
    CandidateSimulationSummary,
    CurrentTaskResponse,
    ProgressSummary,
)
from app.schemas.task import TaskPublic
from app.utils.progress import compute_current_task, summarize_progress

router = APIRouter()


@router.get("/session/{token}", response_model=CandidateSessionResolveResponse)
async def resolve_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateSessionResolveResponse:
    """Resolve an invite token into a candidate session context.

    No auth: possession of the token is the access mechanism.
    On first access, transitions status from not_started -> in_progress and sets started_at.
    If expired, returns 410 with a safe error message.
    """
    stmt = (
        select(CandidateSession)
        .where(CandidateSession.token == token)
        .options(selectinload(CandidateSession.simulation))
    )
    res = await db.execute(stmt)
    cs = res.scalar_one_or_none()

    if cs is None:
        raise HTTPException(status_code=404, detail="Invalid invite token")

    now = datetime.now(UTC)

    expires_at = cs.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at is not None and expires_at < now:
        raise HTTPException(status_code=410, detail="Invite token expired")

    if cs.status == "not_started":
        cs.status = "in_progress"
        if cs.started_at is None:
            cs.started_at = now
        await db.commit()
        await db.refresh(cs)

    sim = cs.simulation
    return CandidateSessionResolveResponse(
        candidateSessionId=cs.id,
        status=cs.status,
        startedAt=cs.started_at,
        completedAt=cs.completed_at,
        candidateName=cs.candidate_name,
        simulation=CandidateSimulationSummary(
            id=sim.id,
            title=sim.title,
            role=sim.role,
        ),
    )


@router.get(
    "/session/{candidate_session_id}/current_task",
    response_model=CurrentTaskResponse,
)
async def get_current_task(
    candidate_session_id: int,
    x_candidate_token: Annotated[str, Header(..., alias="x-candidate-token")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTaskResponse:
    """Return the current task for a candidate session.

    The current task is defined as the lowest day_index task
    that does not yet have a submission from this candidate.
    """
    stmt = select(CandidateSession).where(CandidateSession.id == candidate_session_id)
    res = await db.execute(stmt)
    cs = res.scalar_one_or_none()

    if cs is None:
        raise HTTPException(status_code=404, detail="Candidate session not found")

    if cs.token != x_candidate_token:
        raise HTTPException(status_code=404, detail="Candidate session not found")

    now = datetime.now(UTC)

    expires_at = cs.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at is not None and expires_at < now:
        raise HTTPException(status_code=410, detail="Invite token expired")

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

    current_task = compute_current_task(tasks, completed_task_ids)
    completed, total, is_complete = summarize_progress(len(tasks), completed_task_ids)

    if is_complete and cs.status != "completed":
        cs.status = "completed"
        if cs.completed_at is None:
            cs.completed_at = now
        await db.commit()
        await db.refresh(cs)

    return CurrentTaskResponse(
        candidateSessionId=cs.id,
        status=cs.status,
        currentDayIndex=None if is_complete else current_task.day_index,
        currentTask=(
            None
            if is_complete
            else TaskPublic(
                id=current_task.id,
                dayIndex=current_task.day_index,
                title=current_task.title,
                type=current_task.type,
                description=current_task.description,
            )
        ),
        completedTaskIds=sorted(completed_task_ids),
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )
