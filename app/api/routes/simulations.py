from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.notifications import get_email_service
from app.domains import CandidateSession
from app.domains.candidate_sessions.schemas import (
    CandidateInviteRequest,
    CandidateInviteResponse,
    CandidateSessionListItem,
)
from app.domains.notifications import service as notification_service
from app.domains.simulations import service as sim_service
from app.domains.simulations.schemas import (
    SimulationCreate,
    SimulationCreateResponse,
    SimulationDetailResponse,
    SimulationDetailTask,
    SimulationListItem,
    TaskOut,
)
from app.domains.simulations.simulation import Simulation
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.roles import ensure_recruiter_or_none
from app.services.email import EmailService

router = APIRouter()


@router.get("", response_model=list[SimulationListItem], status_code=status.HTTP_200_OK)
async def list_simulations(
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """List simulations for recruiter dashboard (scoped to current user)."""
    ensure_recruiter_or_none(user)
    rows = await sim_service.list_simulations(db, user.id)

    return [
        SimulationListItem(
            id=sim.id,
            title=sim.title,
            role=sim.role,
            techStack=sim.tech_stack,
            templateKey=sim.template_key,
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
    ensure_recruiter_or_none(user)

    sim, created_tasks = await sim_service.create_simulation_with_tasks(
        db, payload, user
    )

    return SimulationCreateResponse(
        id=sim.id,
        title=sim.title,
        role=sim.role,
        techStack=sim.tech_stack,
        seniority=sim.seniority,
        focus=sim.focus,
        templateKey=sim.template_key,
        tasks=[
            TaskOut(id=t.id, day_index=t.day_index, type=t.type, title=t.title)
            for t in created_tasks
        ],
    )


@router.get(
    "/{simulation_id}",
    response_model=SimulationDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_simulation_detail(
    simulation_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """Return a simulation detail view for recruiters."""
    ensure_recruiter_or_none(user)
    sim, tasks = await sim_service.require_owned_simulation_with_tasks(
        db, simulation_id, user.id
    )

    return SimulationDetailResponse(
        id=sim.id,
        title=sim.title,
        templateKey=sim.template_key,
        role=sim.role,
        techStack=sim.tech_stack,
        focus=sim.focus,
        scenario=sim.scenario_template,
        tasks=[
            SimulationDetailTask(
                dayIndex=task.day_index,
                title=task.title,
                type=task.type,
                description=task.description,
                rubric=None,
                maxScore=task.max_score,
                templateRepoFullName=(
                    task.template_repo
                    if task.day_index in {2, 3} and task.template_repo
                    else None
                ),
            )
            for task in tasks
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
    email_service: Annotated[EmailService, Depends(get_email_service)],
):
    """Create a candidate_session invite token for a simulation (recruiter-only)."""
    ensure_recruiter_or_none(user)

    sim = await sim_service.require_owned_simulation(db, simulation_id, user.id)
    cs = await sim_service.create_invite(
        db, simulation_id, payload, now=datetime.now(UTC)
    )
    await notification_service.send_invite_email(
        db,
        candidate_session=cs,
        simulation=sim,
        invite_url=sim_service.invite_url(cs.token),
        email_service=email_service,
        now=datetime.now(UTC),
    )
    return CandidateInviteResponse(
        candidateSessionId=cs.id,
        token=cs.token,
        inviteUrl=sim_service.invite_url(cs.token),
    )


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
    ensure_recruiter_or_none(user)

    await sim_service.require_owned_simulation(db, simulation_id, user.id)
    rows = await sim_service.list_candidates_with_profile(db, simulation_id)

    return [
        CandidateSessionListItem(
            candidateSessionId=cs.id,
            inviteEmail=cs.invite_email,
            candidateName=cs.candidate_name,
            status=cs.status,
            startedAt=cs.started_at,
            completedAt=cs.completed_at,
            hasFitProfile=(profile_id is not None),
            inviteEmailStatus=getattr(cs, "invite_email_status", None),
            inviteEmailSentAt=getattr(cs, "invite_email_sent_at", None),
            inviteEmailError=getattr(cs, "invite_email_error", None),
        )
        for cs, profile_id in rows
    ]


@router.post(
    "/{simulation_id}/candidates/{candidate_session_id}/invite/resend",
    status_code=status.HTTP_200_OK,
)
async def resend_candidate_invite(
    simulation_id: int,
    candidate_session_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
):
    """Resend an invite email for a candidate session (recruiter-only)."""
    ensure_recruiter_or_none(user)
    sim: Simulation = await sim_service.require_owned_simulation(
        db, simulation_id, user.id
    )
    cs = await db.get(CandidateSession, candidate_session_id)
    if cs is None or cs.simulation_id != sim.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate session not found",
        )

    await notification_service.send_invite_email(
        db,
        candidate_session=cs,
        simulation=sim,
        invite_url=sim_service.invite_url(cs.token),
        email_service=email_service,
        now=datetime.now(UTC),
    )
    return {
        "inviteEmailStatus": getattr(cs, "invite_email_status", None),
        "inviteEmailSentAt": getattr(cs, "invite_email_sent_at", None),
        "inviteEmailError": getattr(cs, "invite_email_error", None),
    }
