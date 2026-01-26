from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.simulations_routes.detail_render import render_simulation_detail
from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter_or_none
from app.core.db import get_session
from app.domains.simulations import service as sim_service
from app.domains.simulations.schemas import SimulationDetailResponse

router = APIRouter()


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
    return render_simulation_detail(sim, tasks)
