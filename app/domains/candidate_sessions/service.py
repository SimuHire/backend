from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.progress import (
    compute_current_task,
    summarize_progress,
)


async def fetch_by_token(
    db: AsyncSession, token: str, *, now: datetime | None = None
) -> CandidateSession:
    """Load a candidate session by invite token or raise 404/410."""
    cs = await cs_repo.get_by_token(db, token, with_simulation=True)
    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite token"
        )

    _ensure_not_expired(cs, now=now)
    return cs


async def fetch_by_id_and_token(
    db: AsyncSession, session_id: int, token: str, *, now: datetime | None = None
) -> CandidateSession:
    """Load a candidate session by id + token or raise 404/410."""
    cs = await cs_repo.get_by_id(db, session_id)

    if cs is None or cs.token != token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate session not found"
        )

    _ensure_not_expired(cs, now=now)
    return cs


async def load_tasks(db: AsyncSession, simulation_id: int) -> list[Task]:
    """Fetch ordered tasks for a simulation or raise if missing."""
    tasks = await cs_repo.tasks_for_simulation(db, simulation_id)

    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulation has no tasks",
        )
    return tasks


async def completed_task_ids(db: AsyncSession, candidate_session_id: int) -> set[int]:
    """Return ids of tasks already submitted for this session."""
    return await cs_repo.completed_task_ids(db, candidate_session_id)


async def progress_snapshot(
    db: AsyncSession, candidate_session: CandidateSession
) -> tuple[list[Task], set[int], Task | None, int, int, bool]:
    """Return tasks, completed ids, current task, and progress summary."""
    tasks = await load_tasks(db, candidate_session.simulation_id)
    completed_ids = await completed_task_ids(db, candidate_session.id)
    current = compute_current_task(tasks, completed_ids)
    completed, total, is_complete = summarize_progress(len(tasks), completed_ids)
    return tasks, completed_ids, current, completed, total, is_complete


def _ensure_not_expired(
    candidate_session: CandidateSession, *, now: datetime | None = None
) -> None:
    """Raise 410 when the candidate session invite has expired."""
    now = now or datetime.now(UTC)
    expires_at = candidate_session.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at is not None and expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invite token expired",
        )
