from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.simulation import Simulation
from app.models.task import Task
from app.schemas.simulation import SimulationCreate, SimulationCreateResponse, TaskOut
from app.security.current_user import get_current_user
from app.services.simulation_blueprint import DEFAULT_5_DAY_BLUEPRINT

router = APIRouter()


@router.get("", status_code=status.HTTP_200_OK)
async def list_simulations():
    """List available simulations (placeholder)."""
    return []


@router.post(
    "", response_model=SimulationCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_simulation(
    payload: SimulationCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """Create a simulation and seed default tasks."""
    # If get_current_user already enforces recruiter, you can remove this.
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
