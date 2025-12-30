from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.progress import (
    compute_current_task,
    summarize_progress,
)

_ACCESS_TOKEN_TTL = timedelta(minutes=30)


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

    _ensure_access_token_valid(cs, token)

    _ensure_not_expired(cs, now=now)
    _ensure_access_token_not_expired(cs, now=now)
    return cs


async def verify_email_and_issue_token(
    db: AsyncSession,
    invite_token: str,
    email: str,
    *,
    now: datetime | None = None,
) -> CandidateSession:
    """Verify invite email and issue a short-lived candidate access token."""
    now = now or datetime.now(UTC)
    cs = await fetch_by_token(db, invite_token, now=now)

    if cs.invite_email.lower() != email.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invite email verification failed",
        )

    _mark_in_progress(cs, now=now)
    _issue_access_token(cs, now=now)
    await db.commit()
    await db.refresh(cs)
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


def _ensure_access_token_valid(
    candidate_session: CandidateSession | None, token: str
) -> None:
    """Raise 404 when the access token does not match or is missing."""
    if (
        candidate_session is None
        or not candidate_session.access_token
        or candidate_session.access_token != token
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate session not found"
        )


def _ensure_access_token_not_expired(
    candidate_session: CandidateSession, *, now: datetime | None = None
) -> None:
    """Raise 401 when the candidate access token is expired."""
    now = now or datetime.now(UTC)
    expires_at = candidate_session.access_token_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at is None or expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Candidate token expired",
        )


def _mark_in_progress(candidate_session: CandidateSession, *, now: datetime) -> None:
    """Transition candidate session to in_progress and set started_at."""
    if candidate_session.status == "not_started":
        candidate_session.status = "in_progress"
        if candidate_session.started_at is None:
            candidate_session.started_at = now


def _issue_access_token(candidate_session: CandidateSession, *, now: datetime) -> None:
    """Generate and attach a new access token with expiry."""
    candidate_session.access_token = secrets.token_urlsafe(32)
    candidate_session.access_token_expires_at = now + _ACCESS_TOKEN_TTL
