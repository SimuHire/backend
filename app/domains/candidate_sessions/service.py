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
from app.domains.candidate_sessions.schemas import (
    CandidateInviteListItem,
    ProgressSummary,
)
from app.infra.security.principal import Principal


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


async def fetch_by_token_for_update(
    db: AsyncSession, token: str, *, now: datetime | None = None
) -> CandidateSession:
    """Load a candidate session by invite token with row lock or raise 404/410."""
    cs = await cs_repo.get_by_token_for_update(db, token)
    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite token"
        )
    _ensure_not_expired(cs, now=now)
    return cs


def _normalize_email(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _ensure_email_verified(principal: Principal) -> None:
    verified = principal.claims.get("email_verified")
    if verified is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )


def _ensure_candidate_ownership(
    candidate_session: CandidateSession, principal: Principal, *, now: datetime
) -> bool:
    """Ensure candidate owns the session, claiming it if unassigned."""
    stored_sub = getattr(candidate_session, "candidate_auth0_sub", None)
    if stored_sub:
        if stored_sub != principal.sub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate session not found",
            )
        changed = False
        email = _normalize_email(principal.email)
        if email and getattr(candidate_session, "candidate_auth0_email", None) is None:
            candidate_session.candidate_auth0_email = email
            changed = True
        if email and candidate_session.candidate_email != email:
            candidate_session.candidate_email = email
            changed = True
        return changed

    _ensure_email_verified(principal)
    email = _normalize_email(principal.email)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email claim missing",
        )

    invite_email = _normalize_email(candidate_session.invite_email)
    if invite_email != email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate session not found",
        )

    candidate_session.candidate_auth0_sub = principal.sub
    candidate_session.candidate_auth0_email = email
    candidate_session.candidate_email = email
    if getattr(candidate_session, "claimed_at", None) is None:
        candidate_session.claimed_at = now
    return True


async def claim_invite_with_principal(
    db: AsyncSession, token: str, principal: Principal, *, now: datetime | None = None
) -> CandidateSession:
    """Attach Auth0 identity to an invite token and transition to in_progress."""
    now = now or datetime.now(UTC)
    async with db.begin_nested():
        cs = await fetch_by_token_for_update(db, token, now=now)
        _mark_in_progress(cs, now=now)
        changed = _ensure_candidate_ownership(cs, principal, now=now)
    if changed:
        await db.commit()
        await db.refresh(cs)
    return cs


async def invite_list_for_principal(
    db: AsyncSession, principal: Principal
) -> list[CandidateInviteListItem]:
    """Return candidate invite summaries for the authenticated candidate."""
    email = _normalize_email(principal.email)
    sessions = await cs_repo.list_for_email(db, email)
    items: list[CandidateInviteListItem] = []
    now = datetime.now(UTC)
    for cs in sessions:
        expires_at = cs.expires_at
        is_expired = False
        if expires_at is not None:
            exp = (
                expires_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None
                else expires_at
            )
            is_expired = exp < now
        progress_tasks = await progress_snapshot(db, cs)
        (
            tasks,
            completed_ids,
            _current,
            completed,
            total,
            _is_complete,
        ) = progress_tasks
        last_submitted_at = await cs_repo.last_submission_at(db, cs.id)
        last_activity = last_submitted_at or cs.completed_at or cs.started_at
        sim = cs.simulation
        company_name = getattr(sim.company, "name", None) if sim else None
        items.append(
            CandidateInviteListItem(
                candidateSessionId=cs.id,
                simulationId=sim.id if sim else cs.simulation_id,
                simulationTitle=sim.title if sim else "",
                role=sim.role if sim else "",
                companyName=company_name,
                status=cs.status,
                progress=ProgressSummary(completed=completed, total=total),
                lastActivityAt=last_activity,
                inviteCreatedAt=getattr(cs, "created_at", None),
                expiresAt=cs.expires_at,
                inviteToken=cs.token,
                isExpired=is_expired,
            )
        )
    return items


async def fetch_owned_session(
    db: AsyncSession,
    session_id: int,
    principal: Principal,
    *,
    now: datetime | None = None,
) -> CandidateSession:
    """Load a candidate session and enforce Auth0 ownership."""
    now = now or datetime.now(UTC)
    cs = await cs_repo.get_by_id(db, session_id)
    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate session not found"
        )

    _ensure_not_expired(cs, now=now)
    stored_sub = getattr(cs, "candidate_auth0_sub", None)
    if stored_sub:
        if stored_sub != principal.sub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate session not found",
            )
        changed = False
        email = _normalize_email(principal.email)
        if email and getattr(cs, "candidate_auth0_email", None) is None:
            cs.candidate_auth0_email = email
            changed = True
        if email and cs.candidate_email != email:
            cs.candidate_email = email
            changed = True
        if cs.status == "not_started":
            _mark_in_progress(cs, now=now)
            changed = True
        if changed:
            await db.commit()
            await db.refresh(cs)
        return cs

    changed = False
    async with db.begin_nested():
        cs = await cs_repo.get_by_id_for_update(db, session_id)
        if cs is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate session not found",
            )
        _ensure_not_expired(cs, now=now)
        if cs.candidate_auth0_sub and cs.candidate_auth0_sub != principal.sub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate session not found",
            )
        changed = _ensure_candidate_ownership(cs, principal, now=now)
        if cs.status == "not_started":
            _mark_in_progress(cs, now=now)
            changed = True
    if changed:
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


def _mark_in_progress(candidate_session: CandidateSession, *, now: datetime) -> None:
    """Transition candidate session to in_progress and set started_at."""
    if candidate_session.status == "not_started":
        candidate_session.status = "in_progress"
        if candidate_session.started_at is None:
            candidate_session.started_at = now
