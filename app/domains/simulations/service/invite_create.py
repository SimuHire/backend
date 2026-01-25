from __future__ import annotations
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.schemas import CandidateInviteRequest
from .invite_tokens import INVITE_TOKEN_TTL_DAYS

async def create_invite(
    db: AsyncSession,
    simulation_id: int,
    payload: CandidateInviteRequest,
    *,
    now: datetime | None = None,
) -> tuple[CandidateSession, bool]:
    now = now or datetime.now(UTC)
    invite_email = str(payload.inviteEmail).strip().lower()
    expires_at = now + timedelta(days=INVITE_TOKEN_TTL_DAYS)
    for _ in range(3):
        token = secrets.token_urlsafe(32)
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
