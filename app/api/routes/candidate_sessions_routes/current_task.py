from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate_sessions import service as cs_service
from app.domains.candidate_sessions.schemas import CurrentTaskResponse
from app.api.routes.candidate_sessions_routes.rate_limits import (
    CANDIDATE_CURRENT_TASK_RATE_LIMIT,
)
from app.api.routes.candidate_sessions_routes.responses import (
    build_current_task_response,
    utcnow,
)
from app.infra.db import get_session
from app.infra.security import rate_limit
from app.infra.security.candidate_access import require_candidate_principal
from app.infra.security.principal import Principal

router = APIRouter()


@router.get("/session/{candidate_session_id}/current_task", response_model=CurrentTaskResponse)
async def get_current_task(
    candidate_session_id: Annotated[int, Path(..., ge=1)],
    request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTaskResponse:
    """Return the current task for a candidate session."""
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_current_task",
            str(candidate_session_id),
            rate_limit.client_id(request),
        )
        rate_limit.limiter.allow(key, CANDIDATE_CURRENT_TASK_RATE_LIMIT)
    now = utcnow()
    cs = await cs_service.fetch_owned_session(db, candidate_session_id, principal, now=now)
    tasks, completed_ids, current_task, completed, total, is_complete = await cs_service.progress_snapshot(
        db, cs
    )
    if is_complete and cs.status != "completed":
        cs.status = "completed"
        if cs.completed_at is None:
            cs.completed_at = now
        await db.commit()
        await db.refresh(cs)
    return build_current_task_response(cs, current_task, completed_ids, completed, total, is_complete)
