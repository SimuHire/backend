from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.auth_tokens import hash_token
from app.infra.db import get_session
from app.infra.security.principal import Principal, bearer_scheme, get_principal


def _is_expired(dt: datetime | None, *, now: datetime) -> bool:
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt < now


async def _lookup_candidate_token(
    db: AsyncSession, token: str, *, now: datetime
) -> CandidateSession | None:
    """Return candidate session if token is valid and unexpired."""
    token_hash = hash_token(token)
    cs = await cs_repo.get_by_access_token_hash(db, token_hash)
    if cs is None:
        return None
    if _is_expired(getattr(cs, "candidate_access_token_expires_at", None), now=now):
        return None
    return cs


async def require_candidate_principal(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Principal:
    """Allow either candidate access token or Auth0 candidate bearer."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    token = credentials.credentials or ""
    now = datetime.now(UTC)

    # Candidate access tokens are opaque without a colon.
    if ":" not in token:
        cs = await _lookup_candidate_token(db, token, now=now)
        if cs is not None:
            return Principal(
                sub=f"candidate-access:{cs.id}",
                email=cs.invite_email,
                name=cs.candidate_name or (cs.invite_email.split("@")[0]),
                roles=[],
                permissions=["candidate:access"],
                claims={
                    "sub": f"candidate-access:{cs.id}",
                    "email": cs.invite_email,
                    "https://simuhire.com/email": cs.invite_email,
                    "permissions": ["candidate:access"],
                    "candidate_session_id": cs.id,
                },
            )

    if ":" in token:
        kind, value = token.split(":", 1)
        if kind == "candidate" and value:
            email = value.strip()
            return Principal(
                sub=f"candidate-stub:{email}",
                email=email,
                name=email.split("@")[0],
                roles=[],
                permissions=["candidate:access"],
                claims={
                    "sub": f"candidate-stub:{email}",
                    "email": email,
                    "https://simuhire.com/email": email,
                    "permissions": ["candidate:access"],
                },
            )

    # Fallback to Auth0 / existing principal handling.
    principal = await get_principal(credentials)
    if "candidate:access" not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate access required",
        )
    return principal
