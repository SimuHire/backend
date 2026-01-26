from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Task
from app.domains.candidate_sessions.schemas import (
    CandidateInviteListItem,
    ProgressSummary,
)
from app.services.candidate_sessions.progress import progress_snapshot


async def build_invite_item(
    db: AsyncSession,
    candidate_session,
    *,
    now: datetime,
    last_submitted_map: dict[int, datetime | None],
    tasks_loader: Callable[[int], Awaitable[list[Task]]],
) -> CandidateInviteListItem:
    expires_at = candidate_session.expires_at
    expires_at = (
        expires_at.replace(tzinfo=UTC)
        if expires_at and expires_at.tzinfo is None
        else expires_at
    )
    is_expired = bool(expires_at and expires_at < now)
    task_list = await tasks_loader(candidate_session.simulation_id)
    _, completed_ids, _, completed, total, _ = await progress_snapshot(
        db, candidate_session, tasks=task_list
    )
    last_submitted_at = last_submitted_map.get(candidate_session.id)
    last_activity = (
        last_submitted_at
        or candidate_session.completed_at
        or candidate_session.started_at
    )
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
