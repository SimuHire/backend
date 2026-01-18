from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
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
from app.infra.security import rate_limit
from app.infra.security.candidate_access import require_candidate_principal
from app.infra.security.principal import Principal

router = APIRouter()

CANDIDATE_CLAIM_RATE_LIMIT = rate_limit.RateLimitRule(limit=10, window_seconds=60.0)
CANDIDATE_CURRENT_TASK_RATE_LIMIT = rate_limit.RateLimitRule(
    limit=60, window_seconds=60.0
)
CANDIDATE_INVITES_RATE_LIMIT = rate_limit.RateLimitRule(limit=30, window_seconds=60.0)


@router.get("/session/{token}", response_model=CandidateSessionResolveResponse)
async def resolve_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateSessionResolveResponse:
    """Claim an invite token for the authenticated candidate."""
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_claim",
            rate_limit.client_id(request),
            rate_limit.hash_value(token),
        )
        rate_limit.limiter.allow(key, CANDIDATE_CLAIM_RATE_LIMIT)
    cs = await cs_service.claim_invite_with_principal(
        db, token, principal, now=datetime.now(UTC)
    )
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
async def claim_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_candidate_principal)],
) -> CandidateSessionResolveResponse:
    """Idempotent claim endpoint for authenticated candidates (no email body required)."""
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_claim",
            rate_limit.client_id(request),
            rate_limit.hash_value(token),
        )
        rate_limit.limiter.allow(key, CANDIDATE_CLAIM_RATE_LIMIT)
    now = datetime.now(UTC)
    cs = await cs_service.claim_invite_with_principal(db, token, principal, now=now)

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
    candidate_session_id: Annotated[int, Path(..., ge=1)],
    request: Request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTaskResponse:
    """Return the current task for a candidate session.

    The current task is defined as the lowest day_index task
    that does not yet have a submission from this candidate.
    """
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_current_task",
            str(candidate_session_id),
            rate_limit.client_id(request),
        )
        rate_limit.limiter.allow(key, CANDIDATE_CURRENT_TASK_RATE_LIMIT)
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
    request: Request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[CandidateInviteListItem]:
    """List all invites for the authenticated candidate email."""
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_invites",
            rate_limit.hash_value(principal.sub),
            rate_limit.client_id(request),
        )
        rate_limit.limiter.allow(key, CANDIDATE_INVITES_RATE_LIMIT)
    return await cs_service.invite_list_for_principal(db, principal)
