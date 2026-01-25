from __future__ import annotations
from datetime import UTC, datetime
from typing import Awaitable, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains import Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.schemas import CandidateInviteListItem, ProgressSummary
from app.domains.candidate_sessions.service.progress import progress_snapshot


async def build_invite_item(
    db: AsyncSession,
    candidate_session,
    *,
    now: datetime,
    last_submitted_map: dict[int, datetime | None],
    tasks_loader: Callable[[int], Awaitable[list[Task]]],
) -> CandidateInviteListItem:
    expires_at = candidate_session.expires_at
    exp = expires_at.replace(tzinfo=UTC) if expires_at and expires_at.tzinfo is None else expires_at
    is_expired = bool(exp and exp < now)
    task_list = await tasks_loader(candidate_session.simulation_id)
    _, completed_ids, _, completed, total, _ = await progress_snapshot(db, candidate_session, tasks=task_list)
    last_submitted_at = last_submitted_map.get(candidate_session.id)
    last_activity = last_submitted_at or candidate_session.completed_at or candidate_session.started_at
    sim = candidate_session.simulation
    company_name = getattr(sim.company, "name", None) if sim else None
    return CandidateInviteListItem(
        candidateSessionId=candidate_session.id,
        simulationId=sim.id if sim else candidate_session.simulation_id,
        simulationTitle=sim.title if sim else "",
        role=sim.role if sim else "",
        companyName=company_name,
        status=candidate_session.status,
        progress=ProgressSummary(completed=completed, total=total),
        lastActivityAt=last_activity,
        inviteCreatedAt=getattr(candidate_session, "created_at", None),
        expiresAt=candidate_session.expires_at,
        inviteToken=candidate_session.token,
        isExpired=is_expired,
    )


async def last_submission_map(db: AsyncSession, session_ids: list[int]) -> dict[int, datetime | None]:
    return await cs_repo.last_submission_at_bulk(db, session_ids)
