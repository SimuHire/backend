from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.service.status import require_not_expired


async def fetch_by_token(db: AsyncSession, token: str, *, now=None) -> CandidateSession:
    cs = await cs_repo.get_by_token(db, token, with_simulation=True)
    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite token"
        )
    require_not_expired(cs, now=now)
    return cs


async def fetch_by_token_for_update(
    db: AsyncSession, token: str, *, now=None
) -> CandidateSession:
    cs = await cs_repo.get_by_token_for_update(db, token)
    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite token"
        )
    require_not_expired(cs, now=now)
    return cs


__all__ = ["fetch_by_token", "fetch_by_token_for_update"]
