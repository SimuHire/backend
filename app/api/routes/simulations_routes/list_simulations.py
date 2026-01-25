from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.simulations import service as sim_service
from app.domains.simulations.schemas import SimulationListItem
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.roles import ensure_recruiter_or_none

router = APIRouter(prefix="/simulations")


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
