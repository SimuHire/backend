from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.notifications import get_email_service
from app.api.routers.simulations_routes.invite_render import render_invite_status
from app.api.routers.simulations_routes.invite_resend_logic import resend_invite
from app.core.auth.current_user import get_current_user
from app.core.db import get_session
from app.services.email import EmailService

router = APIRouter()


@router.post(
    "/{simulation_id}/candidates/{candidate_session_id}/invite/resend",
    status_code=status.HTTP_200_OK,
)
async def resend_candidate_invite(
    simulation_id: int,
    candidate_session_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
):
    cs = await resend_invite(
        simulation_id=simulation_id,
        candidate_session_id=candidate_session_id,
        request=request,
        db=db,
        user=user,
        email_service=email_service,
    )
    return render_invite_status(cs)
