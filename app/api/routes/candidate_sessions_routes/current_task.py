from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.candidate_sessions_routes.current_task_logic import (
    build_current_task_view,
)
from app.domains.candidate_sessions.schemas import CurrentTaskResponse
from app.infra.db import get_session
from app.infra.security.candidate_access import require_candidate_principal
from app.infra.security.principal import Principal

router = APIRouter()


@router.get(
    "/session/{candidate_session_id}/current_task", response_model=CurrentTaskResponse
)
async def get_current_task(
    candidate_session_id: Annotated[int, Path(..., ge=1)],
    request: Request,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTaskResponse:
    """Return the current task for a candidate session."""
    return await build_current_task_view(candidate_session_id, request, principal, db)
