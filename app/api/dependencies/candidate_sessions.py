from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service


@dataclass(frozen=True)
class CandidateSessionAuth:
    """Headers used to authenticate a candidate session."""

    session_id: int
    token: str


def candidate_headers(
    x_candidate_token: Annotated[str | None, Header(alias="x-candidate-token")] = None,
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id")
    ] = None,
) -> CandidateSessionAuth:
    """Require candidate session headers or raise 401."""
    if not x_candidate_token or x_candidate_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
        )
    return CandidateSessionAuth(
        session_id=int(x_candidate_session_id), token=str(x_candidate_token)
    )


async def fetch_candidate_session(
    db: AsyncSession,
    auth: CandidateSessionAuth,
) -> CandidateSession:
    """Load a candidate session by headers or raise 404/410."""
    return await cs_service.fetch_by_id_and_token(
        db, auth.session_id, auth.token, now=datetime.now(UTC)
    )
