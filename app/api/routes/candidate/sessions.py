from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.candidate_sessions import service as cs_service
from app.domain.candidate_sessions.schemas import (
    CandidateSessionResolveResponse,
    CandidateSimulationSummary,
    CurrentTaskResponse,
    ProgressSummary,
)
from app.domain.simulations.schemas import TaskPublic

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
    now = datetime.now(UTC)
    cs = await cs_service.fetch_by_token(db, token, now=now)

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
    now = datetime.now(UTC)
    cs = await cs_service.fetch_by_id_and_token(
        db, candidate_session_id, x_candidate_token, now=now
    )
    (
        tasks,
        completed_task_ids,
        current_task,
        completed,
        total,
        is_complete,
    ) = await cs_service.progress_snapshot(db, cs)

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
