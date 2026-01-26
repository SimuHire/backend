from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.candidate_sessions_routes.current_task_logic import (
    build_current_task_view,
)
from app.core.auth.candidate_access import require_candidate_principal
from app.core.auth.principal import Principal
from app.core.db import get_session
from app.domains.candidate_sessions.schemas import CurrentTaskResponse

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
