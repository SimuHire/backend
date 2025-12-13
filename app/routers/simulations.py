from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.candidate_session import CandidateSession
from app.models.simulation import Simulation
from app.models.task import Task
from app.schemas.simulation import (
    SimulationCreate,
    SimulationCreateResponse,
    SimulationListItem,
    TaskOut,
)
from app.security.current_user import get_current_user
from app.services.simulation_blueprint import DEFAULT_5_DAY_BLUEPRINT

router = APIRouter()


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
    await db.flush()  # ensures sim.id is populated

    created_tasks: list[Task] = []
    for t in DEFAULT_5_DAY_BLUEPRINT:
        task = Task(
            simulation_id=sim.id,
            day_index=t["day_index"],
            type=t["type"],
            title=t["title"],
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
