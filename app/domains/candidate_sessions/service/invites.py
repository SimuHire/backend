from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains import Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.schemas import CandidateInviteListItem
from app.domains.candidate_sessions.service.invite_items import build_invite_item, last_submission_map
from app.infra.security.principal import Principal


async def invite_list_for_principal(
    db: AsyncSession, principal: Principal
) -> list[CandidateInviteListItem]:
    email = (principal.email or "").strip().lower()
    sessions = await cs_repo.list_for_email(db, email)
    items: list[CandidateInviteListItem] = []
    now = datetime.now(UTC)
    session_ids = [cs.id for cs in sessions]
    last_submitted_map = await last_submission_map(db, session_ids)
    tasks_cache: dict[int, list[Task]] = {}

    async def _tasks_for_simulation(simulation_id: int) -> list[Task]:
        if simulation_id not in tasks_cache:
            tasks_cache[simulation_id] = await cs_repo.tasks_for_simulation(
                db, simulation_id
            )
        return tasks_cache[simulation_id]

    for cs in sessions:
        items.append(
            await build_invite_item(
                db,
                cs,
                now=now,
                last_submitted_map=last_submitted_map,
                tasks_loader=_tasks_for_simulation,
            )
        )
    return items
