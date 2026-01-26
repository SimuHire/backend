from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.principal import Principal
from app.domains.candidate_sessions.service.fetch import fetch_by_token_for_update
from app.domains.candidate_sessions.service.ownership import ensure_candidate_ownership
from app.domains.candidate_sessions.service.status import mark_in_progress


async def claim_invite_with_principal(
    db: AsyncSession, token: str, principal: Principal, *, now: datetime | None = None
):
    now = now or datetime.now(UTC)
    async with db.begin_nested():
        cs = await fetch_by_token_for_update(db, token, now=now)
        mark_in_progress(cs, now=now)
        changed = ensure_candidate_ownership(cs, principal, now=now)
    if changed:
        await db.commit()
        await db.refresh(cs)
    return cs
