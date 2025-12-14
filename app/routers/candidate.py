from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models.candidate_session import CandidateSession
from app.schemas.candidate_session import (
    CandidateSessionResolveResponse,
    CandidateSimulationSummary,
)

router = APIRouter()


@router.get("/session/{token}", response_model=CandidateSessionResolveResponse)
async def resolve_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateSessionResolveResponse:
    """Resolve an invite token into a candidate session context.

    No auth: possession of the token is the access mechanism.
    On first access, transitions status from not_started -> in_progress and sets started_at.
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
