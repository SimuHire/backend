from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession


async def get_by_id(db: AsyncSession, session_id: int) -> CandidateSession | None:
    res = await db.execute(
        select(CandidateSession).where(CandidateSession.id == session_id)
    )
    return res.scalar_one_or_none()


async def get_by_id_for_update(
    db: AsyncSession, session_id: int
) -> CandidateSession | None:
    res = await db.execute(
        select(CandidateSession)
        .where(CandidateSession.id == session_id)
        .with_for_update()
    )
    return res.scalar_one_or_none()


__all__ = ["get_by_id", "get_by_id_for_update"]
