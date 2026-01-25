from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.schemas import CandidateInviteRequest
from app.domains.common.types import CANDIDATE_SESSION_STATUS_COMPLETED

from .invite_errors import InviteRejectedError
from .invite_factory import resolve_create_invite_callable
from .invite_tokens import _invite_is_expired, _refresh_invite_token


async def create_or_resend_invite(
    db: AsyncSession,
    simulation_id: int,
    payload: CandidateInviteRequest,
    *,
    now: datetime | None = None,
) -> tuple:
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

    create_invite_fn = resolve_create_invite_callable()
    created, was_created = await create_invite_fn(
        db, simulation_id=simulation_id, payload=payload, now=now
    )
    if created.status == CANDIDATE_SESSION_STATUS_COMPLETED:
        raise InviteRejectedError()
    if _invite_is_expired(created, now=now):
        refreshed = await _refresh_invite_token(db, created, now=now)
        await db.commit()
        await db.refresh(refreshed)
        return refreshed, "created"
    return created, "created" if was_created else "resent"
