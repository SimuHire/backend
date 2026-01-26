from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter_or_none
from app.core.db import get_session
from app.domains.simulations import service as sim_service
from app.domains.simulations.schemas import (
    SimulationCreate,
    SimulationCreateResponse,
    TaskOut,
)

router = APIRouter(prefix="/simulations")


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
