from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate_sessions import service as cs_service
from app.domains.candidate_sessions.schemas import (
    CandidateInviteListItem,
    CandidateSessionResolveResponse,
    CandidateSimulationSummary,
    CurrentTaskResponse,
    ProgressSummary,
)
from app.domains.tasks.schemas_public import TaskPublic
from app.infra.db import get_session
from app.infra.security.principal import Principal, require_permissions

router = APIRouter()


@router.get("/session/{token}", response_model=CandidateSessionResolveResponse)
async def resolve_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    principal: Annotated[Principal, Depends(require_permissions(["candidate:access"]))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateSessionResolveResponse:
    """Claim an invite token for the authenticated candidate."""
    cs = await cs_service.claim_invite_with_principal(
        db, token, principal, now=datetime.now(UTC)
    )
    await db.refresh(cs, attribute_names=["simulation"])
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


@router.post(
    "/session/{token}/claim",
    response_model=CandidateSessionResolveResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/session/{token}/verify",
    response_model=CandidateSessionResolveResponse,
    status_code=status.HTTP_200_OK,
)
async def claim_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_permissions(["candidate:access"]))],
) -> CandidateSessionResolveResponse:
    """Idempotent claim endpoint for authenticated candidates (no email body required)."""
    now = datetime.now(UTC)
    cs = await cs_service.claim_invite_with_principal(db, token, principal, now=now)
    await db.refresh(cs, attribute_names=["simulation"])

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
    principal: Annotated[Principal, Depends(require_permissions(["candidate:access"]))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTaskResponse:
    """Return the current task for a candidate session.

    The current task is defined as the lowest day_index task
    that does not yet have a submission from this candidate.
    """
    now = datetime.now(UTC)
    cs = await cs_service.fetch_owned_session(
        db, candidate_session_id, principal, now=now
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


@router.get("/invites", response_model=list[CandidateInviteListItem])
async def list_candidate_invites(
    principal: Annotated[Principal, Depends(require_permissions(["candidate:access"]))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[CandidateInviteListItem]:
    """List all invites for the authenticated candidate email."""
    return await cs_service.invite_list_for_principal(db, principal)
