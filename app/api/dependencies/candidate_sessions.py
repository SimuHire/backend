from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.candidate_access import require_candidate_principal
from app.core.auth.principal import Principal
from app.core.db import get_session
from app.core.errors import ApiError
from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service


async def candidate_session_from_headers(
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id", ge=1)
    ] = None,
    db: Annotated[AsyncSession, Depends(get_session)] = None,
) -> CandidateSession:
    """Load a candidate session for the authenticated candidate."""
    if x_candidate_session_id is None:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
            error_code="CANDIDATE_SESSION_HEADER_REQUIRED",
        )
    now = datetime.now(UTC)
    return await cs_service.fetch_owned_session(
        db, int(x_candidate_session_id), principal, now=now
    )
