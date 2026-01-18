from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.domains import CandidateSession, FitProfile, Simulation, Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.schemas import CandidateInviteRequest
from app.domains.common.types import CANDIDATE_SESSION_STATUS_COMPLETED
from app.domains.simulations import repository as sim_repo
from app.domains.simulations.blueprints import DEFAULT_5_DAY_BLUEPRINT
from app.domains.tasks.template_catalog import (
    ALLOWED_TEMPLATE_KEYS,
    DEFAULT_TEMPLATE_KEY,
    TemplateKeyError,
    resolve_template_repo_full_name,
    validate_template_key,
)
from app.infra.config import settings
from app.infra.errors import ApiError

INVITE_TOKEN_TTL_DAYS = 14


class InviteRejectedError(Exception):
    """Raised when an invite cannot be issued because the session is completed."""

    def __init__(
        self,
        *,
        code: str = "candidate_already_completed",
        message: str = "Candidate already completed simulation",
        outcome: str = "rejected",
    ) -> None:
        self.code = code
        self.message = message
        self.outcome = outcome
        super().__init__(message)


async def require_owned_simulation(
    db: AsyncSession, simulation_id: int, user_id: int
) -> Simulation:
    """Return simulation if recruiter owns it; otherwise raise 404."""
    sim = await sim_repo.get_owned(db, simulation_id, user_id)
    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found"
        )
    return sim


async def require_owned_simulation_with_tasks(
    db: AsyncSession, simulation_id: int, user_id: int
) -> tuple[Simulation, list[Task]]:
    """Return simulation + tasks if recruiter owns it; otherwise raise 404."""
    sim, tasks = await sim_repo.get_owned_with_tasks(db, simulation_id, user_id)
    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found"
        )
    return sim, tasks


async def list_simulations(db: AsyncSession, user_id: int):
    """List simulations with candidate counts for a recruiter."""
    return await sim_repo.list_with_candidate_counts(db, user_id)


async def create_simulation_with_tasks(
    db: AsyncSession, payload, user: Any
) -> tuple[Simulation, list[Task]]:
    """Create simulation and seed default tasks."""
    try:
        template_key = validate_template_key(
            getattr(payload, "templateKey", DEFAULT_TEMPLATE_KEY)
            or DEFAULT_TEMPLATE_KEY
        )
    except TemplateKeyError as exc:
        allowed = sorted(ALLOWED_TEMPLATE_KEYS)
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid templateKey. Allowed: " + ", ".join(allowed),
            error_code="INVALID_TEMPLATE_KEY",
            details={"allowed": allowed},
        ) from exc

    sim = Simulation(
        title=payload.title,
        role=payload.role,
        tech_stack=payload.techStack,
        seniority=payload.seniority,
        focus=payload.focus,
        scenario_template="default-5day-node-postgres",
        company_id=user.company_id,
        created_by=user.id,
        template_key=template_key,
    )
    db.add(sim)
    await db.flush()

    created_tasks: list[Task] = []
    for t in DEFAULT_5_DAY_BLUEPRINT:
        template_repo = _template_repo_for_task(t["day_index"], t["type"], template_key)
        task = Task(
            simulation_id=sim.id,
            day_index=t["day_index"],
            type=t["type"],
            title=t["title"],
            description=t["description"],
            template_repo=template_repo,
        )
        db.add(task)
        created_tasks.append(task)

    await db.commit()

    await db.refresh(sim)
    for t in created_tasks:
        await db.refresh(t)

    created_tasks.sort(key=lambda x: x.day_index)
    return sim, created_tasks


def _template_repo_for_task(
    day_index: int, task_type: str, template_key: str
) -> str | None:
    """Resolve a template repo for a seeded task."""
    task_type = (task_type or "").lower()
    if task_type not in {"code", "debug"}:
        return None

    # Most blueprints use day 2/3 for code/debug, but support other days too.
    if day_index not in {2, 3}:
        return resolve_template_repo_full_name(template_key)

    repo = resolve_template_repo_full_name(template_key)

    # Allow overriding owner via env when repo name is provided without owner.
    if "/" not in repo and settings.github.GITHUB_TEMPLATE_OWNER:
        return f"{settings.github.GITHUB_TEMPLATE_OWNER}/{repo}"
    return repo


async def create_invite(
    db: AsyncSession,
    simulation_id: int,
    payload: CandidateInviteRequest,
    *,
    now: datetime | None = None,
) -> tuple[CandidateSession, bool]:
    """Create a candidate session with random token, handling rare collisions."""
    now = now or datetime.now(UTC)
    # Stored emails are normalized to align with unique constraint enforcement.
    invite_email = str(payload.inviteEmail).strip().lower()
    expires_at = now + timedelta(days=INVITE_TOKEN_TTL_DAYS)
    for _ in range(3):
        token = secrets.token_urlsafe(32)  # typically ~43 chars, url-safe
        cs = CandidateSession(
            simulation_id=simulation_id,
            candidate_name=payload.candidateName,
            invite_email=invite_email,
            token=token,
            status="not_started",
            expires_at=expires_at,
        )
        db.add(cs)

        try:
            await db.commit()
            await db.refresh(cs)
            return cs, True
        except IntegrityError:
            await db.rollback()
            existing = await cs_repo.get_by_simulation_and_email(
                db, simulation_id=simulation_id, invite_email=invite_email
            )
            if existing:
                return existing, False

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate invite token",
    )


def _invite_is_expired(candidate_session: CandidateSession, *, now: datetime) -> bool:
    expires_at = candidate_session.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < now


async def _refresh_invite_token(
    db: AsyncSession, candidate_session: CandidateSession, *, now: datetime
) -> CandidateSession:
    expires_at = now + timedelta(days=INVITE_TOKEN_TTL_DAYS)
    for _ in range(3):
        try:
            async with db.begin_nested():
                candidate_session.token = secrets.token_urlsafe(32)
                candidate_session.expires_at = expires_at
                await db.flush()
            return candidate_session
        except IntegrityError:
            continue

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate invite token",
    )


async def create_or_resend_invite(
    db: AsyncSession,
    simulation_id: int,
    payload: CandidateInviteRequest,
    *,
    now: datetime | None = None,
) -> tuple[CandidateSession, str]:
    """Create, refresh, or resend a candidate invite based on existing state."""
    now = now or datetime.now(UTC)
    invite_email = str(payload.inviteEmail).strip().lower()

    existing = await cs_repo.get_by_simulation_and_email_for_update(
        db, simulation_id=simulation_id, invite_email=invite_email
    )
    if existing:
        if existing.status == CANDIDATE_SESSION_STATUS_COMPLETED:
            raise InviteRejectedError()
        if _invite_is_expired(existing, now=now):
            refreshed = await _refresh_invite_token(db, existing, now=now)
            await db.commit()
            await db.refresh(refreshed)
            return refreshed, "created"
        return existing, "resent"

    created, was_created = await create_invite(
        db, simulation_id=simulation_id, payload=payload, now=now
    )
    if was_created:
        return created, "created"
    if created.status == CANDIDATE_SESSION_STATUS_COMPLETED:
        raise InviteRejectedError()
    if _invite_is_expired(created, now=now):
        refreshed = await _refresh_invite_token(db, created, now=now)
        await db.commit()
        await db.refresh(refreshed)
        return refreshed, "created"
    return created, "resent"


async def list_candidates_with_profile(
    db: AsyncSession, simulation_id: int
) -> list[tuple[CandidateSession, int | None]]:
    """Return candidate sessions with attached report id if present."""
    stmt = (
        select(CandidateSession, FitProfile.id)
        .options(
            load_only(
                CandidateSession.id,
                CandidateSession.invite_email,
                CandidateSession.candidate_name,
                CandidateSession.status,
                CandidateSession.started_at,
                CandidateSession.completed_at,
                CandidateSession.invite_email_status,
                CandidateSession.invite_email_sent_at,
                CandidateSession.invite_email_error,
            )
        )
        .outerjoin(
            FitProfile,
            FitProfile.candidate_session_id == CandidateSession.id,
        )
        .where(CandidateSession.simulation_id == simulation_id)
        .order_by(CandidateSession.id.desc())
    )
    rows = (await db.execute(stmt)).all()
    return rows


def invite_url(token: str) -> str:
    """Construct candidate portal URL for an invite token."""
    return f"{settings.CANDIDATE_PORTAL_BASE_URL.rstrip('/')}/candidate/session/{token}"
