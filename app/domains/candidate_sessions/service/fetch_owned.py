from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.service.fetch_owned_helpers import (
    apply_auth_updates,
    ensure_can_access,
)
from app.domains.candidate_sessions.service.ownership import ensure_candidate_ownership
from app.infra.security.principal import Principal


async def fetch_owned_session(
    db: AsyncSession, session_id: int, principal: Principal, *, now=None
) -> CandidateSession:
    now = now or datetime.now(UTC)
    cs = ensure_can_access(await cs_repo.get_by_id(db, session_id), principal, now=now)
    if cs.candidate_auth0_sub:
        if apply_auth_updates(cs, principal, now=now):
            await db.commit()
            await db.refresh(cs)
        return cs

    changed = False
    async with db.begin_nested():
        cs = ensure_can_access(
            await cs_repo.get_by_id_for_update(db, session_id),
            principal,
            now=now,
            allow_missing=False,
        )
        changed = ensure_candidate_ownership(cs, principal, now=now) or changed
        changed = apply_auth_updates(cs, principal, now=now) or changed
    if changed:
        await db.commit()
        await db.refresh(cs)
    return cs


__all__ = ["fetch_owned_session"]
