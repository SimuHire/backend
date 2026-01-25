from __future__ import annotations

from app.domains.simulations.schemas import (
    SimulationDetailResponse,
    SimulationDetailTask,
)


def render_simulation_detail(sim, tasks) -> SimulationDetailResponse:
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
