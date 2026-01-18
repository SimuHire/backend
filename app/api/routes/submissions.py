from __future__ import annotations

import json
import logging
import re
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

_MAX_OUTPUT_CHARS_LIST = 4000
_MAX_OUTPUT_CHARS_DETAIL = 20000

_TOKEN_REDACT_PATTERNS = [
    re.compile(r"gh[pous]_[A-Za-z0-9]{10,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"(Authorization:\s*Bearer)\s+[^\s]+", re.IGNORECASE),
    re.compile(r"(token)\s+[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
]
_OUTPUT_WHITELIST_KEYS = {
    "passed",
    "failed",
    "total",
    "stdout",
    "stderr",
    "summary",
    "runId",
    "run_id",
    "conclusion",
    "timeout",
}


def _derive_test_status(passed: int | None, failed: int | None, output) -> str | None:
    return recruiter_sub_service.derive_test_status(passed, failed, output)


def _redact_text(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for pattern in _TOKEN_REDACT_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(
                lambda match: f"{match.group(1)} [redacted]", redacted
            )
        else:
            redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _truncate_output(
    text: str | None, *, max_chars: int
) -> tuple[str | None, bool | None]:
    if text is None:
        return None, None
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "... (truncated)", True


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_diff_summary(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _build_links(repo_full_name: str | None, commit_sha: str | None, workflow_run_id):
    commit_url = (
        f"https://github.com/{repo_full_name}/commit/{commit_sha}"
        if repo_full_name and commit_sha
        else None
    )
    workflow_url = (
        f"https://github.com/{repo_full_name}/actions/runs/{workflow_run_id}"
        if repo_full_name and workflow_run_id
        else None
    )
    return commit_url, workflow_url


def _build_diff_url(repo_full_name: str | None, diff_summary):
    if not repo_full_name or not isinstance(diff_summary, dict):
        return None
    base = diff_summary.get("base")
    head = diff_summary.get("head")
    if base and head:
        return f"https://github.com/{repo_full_name}/compare/{base}...{head}"
    return None


def _build_test_results(
    sub,
    parsed_output,
    *,
    workflow_url: str | None,
    commit_url: str | None,
    include_output: bool,
    max_output_chars: int,
):
    passed_val = _safe_int(getattr(sub, "tests_passed", None))
    failed_val = _safe_int(getattr(sub, "tests_failed", None))
    workflow_run_id = getattr(sub, "workflow_run_id", None)
    commit_sha = getattr(sub, "commit_sha", None)
    last_run_at = getattr(sub, "last_run_at", None)
    total_val = None
    run_id = None
    run_status = None
    conclusion = None
    timeout = None
    summary = None
    stdout = None
    stderr = None
    stdout_truncated = None
    stderr_truncated = None
    sanitized_output = parsed_output

    if isinstance(parsed_output, dict) and not parsed_output:
        parsed_output = None
        sanitized_output = None

    if isinstance(parsed_output, dict):
        whitelisted_output = {}
        if passed_val is None:
            passed_val = _safe_int(parsed_output.get("passed"))
        if failed_val is None:
            failed_val = _safe_int(parsed_output.get("failed"))
        total_val = _safe_int(parsed_output.get("total"))

        run_id = parsed_output.get("runId") or parsed_output.get("run_id")
        conclusion_raw = parsed_output.get("conclusion")
        conclusion = conclusion or (
            str(conclusion_raw).lower() if conclusion_raw else None
        )
        timeout = timeout or (
            parsed_output.get("timeout") is True or conclusion == "timed_out"
        )
        summary_val = parsed_output.get("summary")
        summary = summary_val if isinstance(summary_val, dict) else None

        stdout_raw = parsed_output.get("stdout")
        stderr_raw = parsed_output.get("stderr")
        if isinstance(stdout_raw, str):
            stdout_clean = _redact_text(stdout_raw)
            stdout, stdout_truncated = _truncate_output(
                stdout_clean, max_chars=max_output_chars
            )
        if isinstance(stderr_raw, str):
            stderr_clean = _redact_text(stderr_raw)
            stderr, stderr_truncated = _truncate_output(
                stderr_clean, max_chars=max_output_chars
            )

        for key in _OUTPUT_WHITELIST_KEYS:
            if key in parsed_output:
                whitelisted_output[key] = parsed_output.get(key)
        if stdout_raw is not None:
            whitelisted_output["stdout"] = stdout
        if stderr_raw is not None:
            whitelisted_output["stderr"] = stderr
        sanitized_output = whitelisted_output if include_output else None
    elif isinstance(parsed_output, str):
        redacted = _redact_text(parsed_output)
        text, truncated = _truncate_output(redacted, max_chars=max_output_chars)
        sanitized_output = text if include_output else None
        stdout_truncated = stdout_truncated or truncated
        stderr_truncated = stderr_truncated or truncated

    if total_val is None and (passed_val is not None or failed_val is not None):
        total_val = (passed_val or 0) + (failed_val or 0)

    status_str = _derive_test_status(passed_val, failed_val, parsed_output)

    if run_id is None and workflow_run_id:
        run_id = _safe_int(workflow_run_id) or workflow_run_id
    if timeout is None and conclusion == "timed_out":
        timeout = True

    if (
        status_str is None
        and passed_val is None
        and failed_val is None
        and total_val is None
        and sanitized_output is None
        and workflow_run_id is None
        and commit_sha is None
        and last_run_at is None
    ):
        return None

    db_status = getattr(sub, "workflow_run_status", None)
    if isinstance(db_status, str):
        db_status = db_status.lower()
    if db_status is not None:
        run_status = db_status

    db_conclusion = getattr(sub, "workflow_run_conclusion", None)
    if isinstance(db_conclusion, str):
        db_conclusion = db_conclusion.lower()
    if db_conclusion is not None:
        conclusion = db_conclusion

    if timeout is None and conclusion == "timed_out":
        timeout = True

    workflow_run_id_str = str(workflow_run_id) if workflow_run_id is not None else None

    artifact_present = (
        parsed_output is not None
        or passed_val is not None
        or failed_val is not None
        or total_val is not None
    )
    artifact_error = None
    if isinstance(parsed_output, dict):
        artifact_error = parsed_output.get("artifactErrorCode") or parsed_output.get(
            "artifact_error_code"
        )
        if isinstance(artifact_error, str):
            artifact_error = artifact_error.lower()

    result = {
        "status": status_str,
        "passed": passed_val,
        "failed": failed_val,
        "total": total_val,
        "runId": run_id,
        "runStatus": run_status,
        "conclusion": conclusion,
        "timeout": timeout,
        "stdout": stdout,
        "stderr": stderr,
        "stdoutTruncated": stdout_truncated,
        "stderrTruncated": stderr_truncated,
        "summary": summary,
        "lastRunAt": last_run_at,
        "workflowRunId": workflow_run_id_str,
        "commitSha": commit_sha,
        "workflowUrl": workflow_url,
        "commitUrl": commit_url,
        "artifactName": "tenon-test-results" if artifact_present else None,
        "artifactPresent": True if artifact_present else None,
        "artifactErrorCode": artifact_error,
    }

    if include_output:
        result["output"] = sanitized_output

    return result


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

    parsed_output = recruiter_sub_service.parse_test_output(
        getattr(sub, "test_output", None)
    )

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

    diff_summary = _parse_diff_summary(sub.diff_summary_json)

    repo_full_name = sub.code_repo_path
    commit_url, workflow_url = _build_links(
        repo_full_name, sub.commit_sha, sub.workflow_run_id
    )
    diff_url = _build_diff_url(repo_full_name, diff_summary)
    test_results = _build_test_results(
        sub,
        parsed_output,
        workflow_url=workflow_url,
        commit_url=commit_url,
        include_output=True,
        max_output_chars=_MAX_OUTPUT_CHARS_DETAIL,
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
        testResults=test_results,
        diffSummary=diff_summary,
        submittedAt=sub.submitted_at,
        workflowUrl=workflow_url,
        commitUrl=commit_url,
        diffUrl=diff_url,
    )


@router.get(
    "",
    response_model=RecruiterSubmissionListOut,
    response_model_exclude={"items": {"__all__": {"testResults": {"output"}}}},
)
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
        parsed_output = recruiter_sub_service.parse_test_output(
            getattr(sub, "test_output", None)
        )
        diff_summary = _parse_diff_summary(sub.diff_summary_json)

        repo_full_name = sub.code_repo_path
        commit_url, workflow_url = _build_links(
            repo_full_name, sub.commit_sha, sub.workflow_run_id
        )
        diff_url = _build_diff_url(repo_full_name, diff_summary)
        test_results = _build_test_results(
            sub,
            parsed_output,
            workflow_url=workflow_url,
            commit_url=commit_url,
            include_output=False,
            max_output_chars=_MAX_OUTPUT_CHARS_LIST,
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
                testResults=test_results,
            )
        )

    return RecruiterSubmissionListOut(items=items)
