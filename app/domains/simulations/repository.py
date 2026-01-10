from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Simulation, Task


async def list_with_candidate_counts(db: AsyncSession, user_id: int):
    """List simulations owned by user with candidate counts."""
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
        .where(Simulation.created_by == user_id)
        .order_by(Simulation.created_at.desc())
    )

    result = await db.execute(stmt)
    return result.all()


async def get_owned(
    db: AsyncSession, simulation_id: int, user_id: int
) -> Simulation | None:
    """Fetch a simulation only if owned by given user."""
    stmt = select(Simulation).where(
        Simulation.id == simulation_id,
        Simulation.created_by == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_owned_with_tasks(
    db: AsyncSession, simulation_id: int, user_id: int
) -> tuple[Simulation | None, list[Task]]:
    """Fetch a simulation with tasks if owned by given user."""
    sim = await get_owned(db, simulation_id, user_id)
    if sim is None:
        return None, []

    tasks_stmt = (
        select(Task).where(Task.simulation_id == sim.id).order_by(Task.day_index.asc())
    )
    tasks = (await db.execute(tasks_stmt)).scalars().all()
    return sim, tasks
