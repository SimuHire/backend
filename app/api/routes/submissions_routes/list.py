from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import User
from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.presenter import present_list_item
from app.domains.submissions.schemas import (
    RecruiterSubmissionListItemOut,
    RecruiterSubmissionListOut,
)
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.roles import ensure_recruiter

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get(
    "",
    response_model=RecruiterSubmissionListOut,
    response_model_exclude={"items": {"__all__": {"testResults": {"output"}}}},
)
async def list_submissions_route(
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    candidateSessionId: int | None = Query(default=None),
    taskId: int | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RecruiterSubmissionListOut:
    """List submissions visible to the recruiter with optional filters."""
    ensure_recruiter(user)
    rows = await recruiter_sub_service.list_submissions(
        db, user.id, candidateSessionId, taskId, limit, offset
    )
    items: list[RecruiterSubmissionListItemOut] = []
    for row in rows:
        sub = row
        task = None
        with suppress(TypeError, ValueError):
            sub, task, *_ = row
        if task is None:
            continue
        payload = present_list_item(sub, task)
        items.append(RecruiterSubmissionListItemOut(**payload))
    return RecruiterSubmissionListOut(items=items)
