from __future__ import annotations

from app.domains import Task
from app.domains.simulations.blueprints import DEFAULT_5_DAY_BLUEPRINT

from .task_templates import _template_repo_for_task


async def seed_default_tasks(db, simulation_id: int, template_key: str) -> list[Task]:
    created_tasks: list[Task] = []
    for blueprint in DEFAULT_5_DAY_BLUEPRINT:
        task = Task(
            simulation_id=simulation_id,
            day_index=blueprint["day_index"],
            type=blueprint["type"],
            title=blueprint["title"],
            description=blueprint["description"],
            template_repo=_template_repo_for_task(
                blueprint["day_index"], blueprint["type"], template_key
            ),
        )
        db.add(task)
        created_tasks.append(task)
    return created_tasks
