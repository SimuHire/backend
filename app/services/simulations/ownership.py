from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Simulation, Task


async def require_owned_simulation(
    db: AsyncSession, simulation_id: int, user_id: int
) -> Simulation:
    from app.domains.simulations import service as sim_service

    sim = await sim_service.sim_repo.get_owned(db, simulation_id, user_id)
    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found"
        )
    return sim


async def require_owned_simulation_with_tasks(
    db: AsyncSession, simulation_id: int, user_id: int
) -> tuple[Simulation, list[Task]]:
    from app.domains.simulations import service as sim_service

    sim, tasks = await sim_service.sim_repo.get_owned_with_tasks(
        db, simulation_id, user_id
    )
    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found"
        )
    return sim, tasks
