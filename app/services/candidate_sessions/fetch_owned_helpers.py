from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.auth.principal import Principal
from app.domains import CandidateSession
from app.domains.candidate_sessions.service.email import normalize_email
from app.domains.candidate_sessions.service.status import (
    mark_in_progress,
    require_not_expired,
)

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Candidate session not found"
)


def ensure_can_access(
    cs: CandidateSession | None, principal: Principal, *, now=None, allow_missing=True
) -> CandidateSession:
    if cs is None and allow_missing:
        raise _NOT_FOUND
    if cs is None:
        raise _NOT_FOUND
    require_not_expired(cs, now=now or datetime.now(UTC))
    if cs.candidate_auth0_sub and cs.candidate_auth0_sub != principal.sub:
        raise _NOT_FOUND
    return cs


def apply_auth_updates(cs: CandidateSession, principal: Principal, *, now) -> bool:
    changed = False
    email = normalize_email(principal.email)
    if email and getattr(cs, "candidate_auth0_email", None) is None:
        cs.candidate_auth0_email = email
        changed = True
    if email and cs.candidate_email != email:
        cs.candidate_email = email
        changed = True
    if cs.status == "not_started":
        mark_in_progress(cs, now=now)
        changed = True
    return changed


__all__ = ["apply_auth_updates", "ensure_can_access"]
