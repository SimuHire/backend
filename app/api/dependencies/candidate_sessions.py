from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions import service as cs_service
from app.infra.db import get_session
from app.infra.security.candidate_access import require_candidate_principal
from app.infra.security.principal import Principal


@dataclass(frozen=True)
class CandidateSessionAuth:
    """Legacy candidate session auth headers."""

    session_id: int
    token: str


def candidate_headers(
    x_candidate_token: Annotated[str | None, Header(alias="x-candidate-token")] = None,
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id")
    ] = None,
) -> CandidateSessionAuth:
    """Backward-compatible header parser for existing callers."""
    if not x_candidate_token or x_candidate_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
        )
    return CandidateSessionAuth(
        session_id=int(x_candidate_session_id), token=str(x_candidate_token)
    )


async def fetch_candidate_session(
    _db: AsyncSession, _auth: CandidateSessionAuth
) -> CandidateSession:
    """Deprecated helper preserved for test monkeypatches."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Candidate token flow deprecated; use Auth0 bearer",
    )


async def candidate_session_from_headers(
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id")
    ] = None,
    db: Annotated[AsyncSession, Depends(get_session)] = None,
) -> CandidateSession:
    """Load a candidate session for the authenticated candidate."""
    if x_candidate_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
        )
    now = datetime.now(UTC)
    claimed_session_id = principal.claims.get("candidate_session_id")
    if claimed_session_id is not None:
        if int(claimed_session_id) != int(x_candidate_session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this invite",
            )
        cs = await cs_repo.get_by_id(db, int(x_candidate_session_id))
        if cs is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate session not found",
            )
        cs_service._ensure_not_expired(cs, now=now)  # type: ignore[attr-defined]
        return cs

    return await cs_service.fetch_owned_session(
        db, int(x_candidate_session_id), principal, now=now
    )
