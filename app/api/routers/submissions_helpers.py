from contextlib import suppress

from app.api.routers.submissions_helpers_guard import ensure_recruiter_guard
from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.presenter import present_detail, present_list_item
from app.domains.submissions.schemas import (
    RecruiterSubmissionDetailOut,
    RecruiterSubmissionListItemOut,
    RecruiterSubmissionListOut,
)


async def get_submission_detail(
    submission_id: int, db, user
) -> RecruiterSubmissionDetailOut:
    ensure_recruiter_guard(user)
    sub, task, cs, sim = await recruiter_sub_service.fetch_detail(
        db, submission_id, user.id
    )
    return RecruiterSubmissionDetailOut(**present_detail(sub, task, cs, sim))


async def list_submissions(
    db,
    user,
    candidateSessionId: int | None = None,
    taskId: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> RecruiterSubmissionListOut:
    ensure_recruiter_guard(user)
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
        items.append(RecruiterSubmissionListItemOut(**present_list_item(sub, task)))
    return RecruiterSubmissionListOut(items=items)


__all__ = ["get_submission_detail", "list_submissions"]
