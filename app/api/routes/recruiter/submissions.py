from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security.current_user import get_current_user
from app.core.security.roles import ensure_recruiter
from app.domain import User
from app.domain.submissions import service_recruiter as recruiter_sub_service
from app.domain.submissions.schemas import (
    RecruiterSubmissionDetailOut,
    RecruiterSubmissionListItemOut,
    RecruiterSubmissionListOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submissions"])


def _derive_test_status(
    passed: int | None, failed: int | None, output: str | None
) -> str | None:
    return recruiter_sub_service.derive_test_status(passed, failed, output)


@router.get("/{submission_id}", response_model=RecruiterSubmissionDetailOut)
async def get_submission_detail(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> RecruiterSubmissionDetailOut:
    """Fetch a single submission's raw artifacts for a recruiter.

    Recruiter must own the underlying simulation. Returns 404 if not found or not authorized.
    """
    ensure_recruiter(user)

    sub, task, cs, sim = await recruiter_sub_service.fetch_detail(
        db, submission_id, user.id
    )

    status_str = _derive_test_status(
        sub.tests_passed, sub.tests_failed, sub.test_output
    )
    total = None
    if sub.tests_passed is not None or sub.tests_failed is not None:
        total = (sub.tests_passed or 0) + (sub.tests_failed or 0)

    logger.info(
        "recruiter_fetch_submission",
        extra={
            "recruiter_id": user.id,
            "submission_id": sub.id,
            "candidate_session_id": cs.id,
            "simulation_id": sim.id,
            "task_id": task.id,
        },
    )

    return RecruiterSubmissionDetailOut(
        submissionId=sub.id,
        candidateSessionId=cs.id,
        task={
            "taskId": task.id,
            "dayIndex": task.day_index,
            "type": task.type,
            "title": getattr(task, "title", None),
            "prompt": getattr(task, "prompt", None),
        },
        contentText=sub.content_text,
        code=(
            {"blob": sub.code_blob, "repoPath": sub.code_repo_path}
            if (sub.code_blob is not None or sub.code_repo_path is not None)
            else None
        ),
        testResults=(
            {
                "status": status_str,
                "passed": sub.tests_passed,
                "failed": sub.tests_failed,
                "total": total,
                "output": sub.test_output,
            }
            if (
                status_str is not None
                or sub.tests_passed is not None
                or sub.tests_failed is not None
                or sub.test_output is not None
            )
            else None
        ),
        submittedAt=sub.submitted_at,
    )


@router.get("", response_model=RecruiterSubmissionListOut)
async def list_submissions(
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    candidateSessionId: int | None = Query(default=None),
    taskId: int | None = Query(default=None),
) -> RecruiterSubmissionListOut:
    """List submissions for recruiter-owned simulations.

    Optional filters: candidateSessionId, taskId.
    """
    ensure_recruiter(user)

    rows = await recruiter_sub_service.list_submissions(
        db, user.id, candidateSessionId, taskId
    )

    items: list[RecruiterSubmissionListItemOut] = []
    for sub, task, _cs, _sim in rows:
        items.append(
            RecruiterSubmissionListItemOut(
                submissionId=sub.id,
                candidateSessionId=sub.candidate_session_id,
                taskId=sub.task_id,
                dayIndex=task.day_index,
                type=task.type,
                submittedAt=sub.submitted_at,
            )
        )

    return RecruiterSubmissionListOut(items=items)
