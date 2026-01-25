from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.domains import CandidateSession

INVITE_TOKEN_TTL_DAYS = 14


def _invite_is_expired(candidate_session: CandidateSession, *, now: datetime) -> bool:
    expires_at = candidate_session.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < now


async def _refresh_invite_token(
    db, candidate_session: CandidateSession, *, now: datetime
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
