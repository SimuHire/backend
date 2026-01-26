from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter
from app.core.db import get_session
from app.domains import User
from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.presenter import present_detail
from app.domains.submissions.schemas import RecruiterSubmissionDetailOut

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("/{submission_id}", response_model=RecruiterSubmissionDetailOut)
async def get_submission_detail_route(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> RecruiterSubmissionDetailOut:
    """Return recruiter-facing detail for a submission."""
    ensure_recruiter(user)
    sub, task, cs, sim = await recruiter_sub_service.fetch_detail(
        db, submission_id, user.id
    )
    payload = present_detail(sub, task, cs, sim)
    return RecruiterSubmissionDetailOut(**payload)
