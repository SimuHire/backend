import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.candidate_session import CandidateSession
from app.models.execution_profile import ExecutionProfile
from app.models.simulation import Simulation
from app.models.task import Task
from app.schemas.candidate_session import (
    CandidateInviteRequest,
    CandidateInviteResponse,
    CandidateSessionListItem,
)
from app.schemas.simulation import (
    SimulationCreate,
    SimulationCreateResponse,
    SimulationListItem,
    TaskOut,
)
from app.security.current_user import get_current_user
from app.services.simulation_blueprint import DEFAULT_5_DAY_BLUEPRINT

router = APIRouter()

INVITE_TOKEN_TTL_DAYS = 14


@router.get("", response_model=list[SimulationListItem], status_code=status.HTTP_200_OK)
async def list_simulations(
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """List simulations for recruiter dashboard (scoped to current user)."""
    if getattr(user, "role", None) not in (None, "recruiter"):
        raise HTTPException(status_code=403, detail="Recruiter access required")

    counts_subq = (
        select(
            CandidateSession.simulation_id.label("simulation_id"),
            func.count(CandidateSession.id).label("num_candidates"),
        )
        .group_by(CandidateSession.simulation_id)
        .subquery()
    )

    stmt = (
        select(
            Simulation,
            func.coalesce(counts_subq.c.num_candidates, 0).label("num_candidates"),
        )
        .outerjoin(counts_subq, counts_subq.c.simulation_id == Simulation.id)
        .where(Simulation.created_by == user.id)
        .order_by(Simulation.created_at.desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        SimulationListItem(
            id=sim.id,
            title=sim.title,
            role=sim.role,
            techStack=sim.tech_stack,
            createdAt=sim.created_at,
            numCandidates=int(num_candidates),
        )
        for sim, num_candidates in rows
    ]


@router.post(
    "", response_model=SimulationCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_simulation(
    payload: SimulationCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """Create a simulation and seed default tasks."""
    if getattr(user, "role", None) not in (None, "recruiter"):
        raise HTTPException(status_code=403, detail="Recruiter access required")

    sim = Simulation(
        title=payload.title,
        role=payload.role,
        tech_stack=payload.techStack,
        seniority=payload.seniority,
        focus=payload.focus,
        scenario_template="default-5day-node-postgres",
        company_id=user.company_id,
        created_by=user.id,
    )

    db.add(sim)
    await db.flush()

    created_tasks: list[Task] = []
    for t in DEFAULT_5_DAY_BLUEPRINT:
        task = Task(
            simulation_id=sim.id,
            day_index=t["day_index"],
            type=t["type"],
            title=t["title"],
            description=t["description"],
        )
        db.add(task)
        created_tasks.append(task)

    await db.commit()

    await db.refresh(sim)
    for t in created_tasks:
        await db.refresh(t)

    created_tasks.sort(key=lambda x: x.day_index)

    return SimulationCreateResponse(
        id=sim.id,
        title=sim.title,
        role=sim.role,
        techStack=sim.tech_stack,
        seniority=sim.seniority,
        focus=sim.focus,
        tasks=[
            TaskOut(id=t.id, day_index=t.day_index, type=t.type, title=t.title)
            for t in created_tasks
        ],
    )


@router.post(
    "/{simulation_id}/invite",
    response_model=CandidateInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate_invite(
    simulation_id: int,
    payload: CandidateInviteRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """Create a candidate_session invite token for a simulation (recruiter-only)."""
    if getattr(user, "role", None) not in (None, "recruiter"):
        raise HTTPException(status_code=403, detail="Recruiter access required")

    # Must exist AND be owned by recruiter
    stmt = select(Simulation).where(
        Simulation.id == simulation_id,
        Simulation.created_by == user.id,
    )
    sim = (await db.execute(stmt)).scalar_one_or_none()
    if sim is None:
        # 404 for both invalid id and "not owned" to avoid leaking ids
        raise HTTPException(status_code=404, detail="Simulation not found")

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=INVITE_TOKEN_TTL_DAYS)
    # Create session with strong random token.
    # Retry a few times on the ultra-rare chance of token collision.
    for _ in range(3):
        token = secrets.token_urlsafe(32)  # typically ~43 chars, url-safe
        cs = CandidateSession(
            simulation_id=simulation_id,
            candidate_name=payload.candidateName,
            invite_email=str(payload.inviteEmail).lower(),
            token=token,
            status="not_started",
            expires_at=expires_at,
        )
        db.add(cs)

        try:
            await db.commit()
            await db.refresh(cs)

            invite_url = (
                f"{settings.CANDIDATE_PORTAL_BASE_URL.rstrip('/')}"
                f"/candidate/session/{token}"
            )
            return CandidateInviteResponse(
                candidateSessionId=cs.id,
                token=token,
                inviteUrl=invite_url,
            )
        except IntegrityError:
            await db.rollback()

    raise HTTPException(status_code=500, detail="Failed to generate invite token")


@router.get(
    "/{simulation_id}/candidates",
    response_model=list[CandidateSessionListItem],
    status_code=status.HTTP_200_OK,
)
async def list_simulation_candidates(
    simulation_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """List candidate sessions for a simulation (recruiter-only)."""
    if getattr(user, "role", None) not in (None, "recruiter"):
        raise HTTPException(status_code=403, detail="Recruiter access required")

    # Match existing ownership model (same as invite)
    sim_stmt = select(Simulation).where(
        Simulation.id == simulation_id,
        Simulation.created_by == user.id,
    )
    sim = (await db.execute(sim_stmt)).scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    stmt = (
        select(CandidateSession, ExecutionProfile.id)
        .outerjoin(
            ExecutionProfile,
            ExecutionProfile.candidate_session_id == CandidateSession.id,
        )
        .where(CandidateSession.simulation_id == simulation_id)
        .order_by(CandidateSession.id.desc())
    )

    rows = (await db.execute(stmt)).all()

    return [
        CandidateSessionListItem(
            candidateSessionId=cs.id,
            inviteEmail=cs.invite_email,
            candidateName=cs.candidate_name,
            status=cs.status,
            startedAt=cs.started_at,
            completedAt=cs.completed_at,
            hasReport=(profile_id is not None),
        )
        for cs, profile_id in rows
    ]
