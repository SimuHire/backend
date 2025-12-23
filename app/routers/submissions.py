from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.candidate_session import CandidateSession
from app.models.simulation import Simulation
from app.models.submission import Submission
from app.models.task import Task
from app.models.user import User
from app.schemas.submission import (
    RecruiterSubmissionDetailOut,
    RecruiterSubmissionListItemOut,
    RecruiterSubmissionListOut,
)
from app.security.current_user import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


def _require_recruiter(user) -> None:
    if getattr(user, "role", None) != "recruiter":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _derive_test_status(
    passed: int | None, failed: int | None, output: str | None
) -> str | None:
    if passed is None and failed is None and (output is None or output.strip() == ""):
        return None
    if failed is not None and failed > 0:
        return "failed"
    if passed is not None and (failed is None or failed == 0):
        return "passed"
    return "unknown"


@router.get("/{submission_id}", response_model=RecruiterSubmissionDetailOut)
async def get_submission_detail(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> RecruiterSubmissionDetailOut:
    """Fetch a single submission's raw artifacts for a recruiter.

    Recruiter must own the underlying simulation. Returns 404 if not found or not authorized.
    """
    _require_recruiter(user)

    stmt = (
        select(Submission, Task, CandidateSession, Simulation)
        .join(Task, Task.id == Submission.task_id)
        .join(CandidateSession, CandidateSession.id == Submission.candidate_session_id)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(Submission.id == submission_id)
        .where(Simulation.created_by == user.id)
    )

    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found")

    sub, task, cs, sim = row

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
    _require_recruiter(user)

    stmt = (
        select(Submission, Task, CandidateSession, Simulation)
        .join(Task, Task.id == Submission.task_id)
        .join(CandidateSession, CandidateSession.id == Submission.candidate_session_id)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(Simulation.created_by == user.id)
        .order_by(Submission.submitted_at.desc())
    )

    if candidateSessionId is not None:
        stmt = stmt.where(Submission.candidate_session_id == candidateSessionId)
    if taskId is not None:
        stmt = stmt.where(Submission.task_id == taskId)

    rows = (await db.execute(stmt)).all()

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
