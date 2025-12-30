from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import User
from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.schemas import (
    RecruiterSubmissionDetailOut,
    RecruiterSubmissionListItemOut,
    RecruiterSubmissionListOut,
)
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.roles import ensure_recruiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submissions"])


def _derive_test_status(passed: int | None, failed: int | None, output) -> str | None:
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

    parsed_output = recruiter_sub_service.parse_test_output(sub.test_output)
    passed_val = sub.tests_passed
    failed_val = sub.tests_failed
    if isinstance(parsed_output, dict):
        if passed_val is None:
            passed_val = int(parsed_output.get("passed") or 0)
        if failed_val is None:
            failed_val = int(parsed_output.get("failed") or 0)
    status_str = _derive_test_status(passed_val, failed_val, parsed_output)
    total = None
    if passed_val is not None or failed_val is not None:
        total = (passed_val or 0) + (failed_val or 0)

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

    diff_summary = None
    if sub.diff_summary_json:
        try:
            diff_summary = json.loads(sub.diff_summary_json)
        except ValueError:
            diff_summary = sub.diff_summary_json

    repo_full_name = sub.code_repo_path
    commit_url = (
        f"https://github.com/{repo_full_name}/commit/{sub.commit_sha}"
        if repo_full_name and sub.commit_sha
        else None
    )
    workflow_url = (
        f"https://github.com/{repo_full_name}/actions/runs/{sub.workflow_run_id}"
        if repo_full_name and sub.workflow_run_id
        else None
    )
    diff_url = None
    if repo_full_name and isinstance(diff_summary, dict):
        base = diff_summary.get("base")
        head = diff_summary.get("head")
        if base and head:
            diff_url = f"https://github.com/{repo_full_name}/compare/{base}...{head}"

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
            {
                "repoPath": sub.code_repo_path,
                "repoFullName": sub.code_repo_path,
                "repoUrl": f"https://github.com/{sub.code_repo_path}"
                if sub.code_repo_path
                else None,
            }
            if sub.code_repo_path is not None
            else None
        ),
        testResults=(
            {
                "status": status_str,
                "passed": passed_val,
                "failed": failed_val,
                "total": total,
                "output": parsed_output,
                "lastRunAt": sub.last_run_at,
                "workflowRunId": sub.workflow_run_id,
                "commitSha": sub.commit_sha,
                "workflowUrl": workflow_url,
                "commitUrl": commit_url,
            }
            if (
                status_str is not None
                or sub.tests_passed is not None
                or sub.tests_failed is not None
                or parsed_output is not None
            )
            else None
        ),
        diffSummary=diff_summary,
        submittedAt=sub.submitted_at,
        workflowUrl=workflow_url,
        commitUrl=commit_url,
        diffUrl=diff_url,
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
        diff_summary = None
        if sub.diff_summary_json:
            try:
                diff_summary = json.loads(sub.diff_summary_json)
            except ValueError:
                diff_summary = sub.diff_summary_json

        repo_full_name = sub.code_repo_path
        commit_url = (
            f"https://github.com/{repo_full_name}/commit/{sub.commit_sha}"
            if repo_full_name and sub.commit_sha
            else None
        )
        workflow_url = (
            f"https://github.com/{repo_full_name}/actions/runs/{sub.workflow_run_id}"
            if repo_full_name and sub.workflow_run_id
            else None
        )
        diff_url = None
        if repo_full_name and isinstance(diff_summary, dict):
            base = diff_summary.get("base")
            head = diff_summary.get("head")
            if base and head:
                diff_url = (
                    f"https://github.com/{repo_full_name}/compare/{base}...{head}"
                )

        items.append(
            RecruiterSubmissionListItemOut(
                submissionId=sub.id,
                candidateSessionId=sub.candidate_session_id,
                taskId=sub.task_id,
                dayIndex=task.day_index,
                type=task.type,
                submittedAt=sub.submitted_at,
                repoFullName=repo_full_name,
                repoUrl=f"https://github.com/{repo_full_name}"
                if repo_full_name
                else None,
                workflowRunId=sub.workflow_run_id,
                commitSha=sub.commit_sha,
                workflowUrl=workflow_url,
                commitUrl=commit_url,
                diffUrl=diff_url,
                diffSummary=diff_summary,
            )
        )

    return RecruiterSubmissionListOut(items=items)
