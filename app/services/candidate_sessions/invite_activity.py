from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candidate_sessions import repository as cs_repo


async def last_submission_map(
    db: AsyncSession, session_ids: list[int]
) -> dict[int, datetime | None]:
    return await cs_repo.last_submission_at_bulk(db, session_ids)


__all__ = ["last_submission_map"]
