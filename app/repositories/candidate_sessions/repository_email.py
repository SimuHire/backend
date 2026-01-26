from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession


async def get_by_simulation_and_email(
    db: AsyncSession, *, simulation_id: int, invite_email: str
) -> CandidateSession | None:
    stmt = (
        select(CandidateSession)
        .where(
            CandidateSession.simulation_id == simulation_id,
            func.lower(CandidateSession.invite_email) == func.lower(invite_email),
        )
        .order_by(CandidateSession.id.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_by_simulation_and_email_for_update(
    db: AsyncSession, *, simulation_id: int, invite_email: str
) -> CandidateSession | None:
    stmt = (
        select(CandidateSession)
        .where(
            CandidateSession.simulation_id == simulation_id,
            func.lower(CandidateSession.invite_email) == func.lower(invite_email),
        )
        .with_for_update()
        .order_by(CandidateSession.id.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


__all__ = [
    "get_by_simulation_and_email",
    "get_by_simulation_and_email_for_update",
]
