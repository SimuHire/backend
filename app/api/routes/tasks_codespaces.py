import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.dependencies.github_native import get_actions_runner, get_github_client
from app.api.error_utils import ApiError, map_github_error
from app.domains import CandidateSession, Task
from app.domains.candidate_sessions import service as cs_service
from app.domains.github_native import GithubClient, GithubError
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.github_native.workspaces import repository as workspace_repo
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.exceptions import WorkspaceMissing
from app.domains.submissions.schemas import (
    CodespaceInitRequest,
    CodespaceInitResponse,
    CodespaceStatusResponse,
    ProgressSummary,
    RunTestsRequest,
    RunTestsResponse,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)
from app.infra.config import settings
from app.infra.db import get_session
from app.infra.security import rate_limit

router = APIRouter()

logger = logging.getLogger(__name__)

_RATE_LIMIT_RULE = {
    "init": rate_limit.RateLimitRule(limit=20, window_seconds=30.0),
    "run": rate_limit.RateLimitRule(limit=20, window_seconds=30.0),
    "poll": rate_limit.RateLimitRule(limit=15, window_seconds=30.0),
    "submit": rate_limit.RateLimitRule(limit=10, window_seconds=30.0),
}
_POLL_MIN_INTERVAL_SECONDS = 2.0
_RUN_CONCURRENCY_LIMIT = 1


def _rate_limit_or_429(candidate_session_id: int, action: str) -> None:
    """Apply a single rate-limit bucket for the given action."""
    if not rate_limit.rate_limit_enabled():
        return
    rule = _RATE_LIMIT_RULE.get(action, rate_limit.RateLimitRule(5, 30.0))
    key = rate_limit.rate_limit_key("tasks", str(candidate_session_id), action)
    rate_limit.limiter.allow(key, rule)


@asynccontextmanager
async def _concurrency_guard(key: str, limit: int):
    if not rate_limit.rate_limit_enabled():
        yield
        return
    async with rate_limit.limiter.concurrency_guard(key, limit):
        yield


async def _compute_current_task(db: AsyncSession, cs: CandidateSession) -> Task | None:
    tasks, _, current, *_ = await cs_service.progress_snapshot(db, cs)
    return current


def _is_canonical_codespace_url(url: str | None) -> bool:
    """Return True if the URL matches the canonical Codespaces deep link."""
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "codespaces.new":
        return False
    query = parse_qs(parsed.query)
    return query.get("quickstart") == ["1"]


@router.post(
    "/{task_id}/codespace/init",
    response_model=CodespaceInitResponse,
    status_code=status.HTTP_200_OK,
)
async def init_codespace(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: CodespaceInitRequest,
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> CodespaceInitResponse:
    """Provision or return a GitHub workspace for the candidate task."""
    cs = candidate_session
    _rate_limit_or_429(cs.id, "init")
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    current_task = await _compute_current_task(db, cs)
    submission_service.ensure_in_order(current_task, task_id)
    submission_service.validate_run_allowed(task)

    now = datetime.now(UTC)
    try:
        workspace = await submission_service.ensure_workspace(
            db,
            candidate_session=cs,
            task=task,
            github_client=github_client,
            github_username=payload.githubUsername,
            repo_prefix=settings.github.GITHUB_REPO_PREFIX,
            template_default_owner=settings.github.GITHUB_TEMPLATE_OWNER
            or settings.github.GITHUB_ORG,
            now=now,
        )
    except GithubError as exc:
        logger.error(
            "github_workspace_create_failed",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "status_code": getattr(exc, "status_code", None),
            },
        )
        raise map_github_error(exc) from exc

    if not workspace.repo_full_name:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace repo not provisioned yet. Please try again.",
            error_code="WORKSPACE_NOT_READY",
            retryable=True,
        )

    canonical_url = submission_service.build_codespace_url(workspace.repo_full_name)
    codespace_url = workspace.codespace_url
    if not _is_canonical_codespace_url(codespace_url):
        if codespace_url != canonical_url:
            workspace.codespace_url = canonical_url
            await db.commit()
            await db.refresh(workspace)
        codespace_url = canonical_url
    return CodespaceInitResponse(
        repoFullName=workspace.repo_full_name,
        repoUrl=f"https://github.com/{workspace.repo_full_name}",
        codespaceUrl=codespace_url,
        defaultBranch=workspace.default_branch,
        workspaceId=workspace.id,
    )


@router.get(
    "/{task_id}/codespace/status",
    response_model=CodespaceStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def codespace_status(
    task_id: Annotated[int, Path(..., ge=1)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CodespaceStatusResponse:
    """Return current workspace status for a task."""
    cs = candidate_session
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)

    workspace = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=cs.id, task_id=task.id
    )
    if workspace is None:
        raise WorkspaceMissing(
            detail="Workspace not initialized", status_code=status.HTTP_404_NOT_FOUND
        )

    last_test_summary = None
    if workspace.last_test_summary_json:
        try:
            last_test_summary = json.loads(workspace.last_test_summary_json)
        except ValueError:
            last_test_summary = None

    if not workspace.repo_full_name:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace repo not provisioned yet. Please try again.",
            error_code="WORKSPACE_NOT_READY",
            retryable=True,
        )

    canonical_url = submission_service.build_codespace_url(workspace.repo_full_name)
    codespace_url = workspace.codespace_url
    if not _is_canonical_codespace_url(codespace_url):
        if codespace_url != canonical_url:
            workspace.codespace_url = canonical_url
            await db.commit()
            await db.refresh(workspace)
        codespace_url = canonical_url

    return CodespaceStatusResponse(
        repoFullName=workspace.repo_full_name,
        repoUrl=f"https://github.com/{workspace.repo_full_name}",
        codespaceUrl=codespace_url,
        defaultBranch=workspace.default_branch,
        latestCommitSha=workspace.latest_commit_sha,
        lastWorkflowRunId=workspace.last_workflow_run_id,
        lastWorkflowConclusion=workspace.last_workflow_conclusion,
        lastTestSummary=last_test_summary,
        workspaceId=workspace.id,
    )


@router.post(
    "/{task_id}/run",
    response_model=RunTestsResponse,
    status_code=status.HTTP_200_OK,
)
async def run_task_tests(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: RunTestsRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
) -> RunTestsResponse:
    """Trigger GitHub Actions tests for a code/debug task."""
    cs = candidate_session
    _rate_limit_or_429(cs.id, "run")
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    submission_service.validate_run_allowed(task)

    workspace = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=cs.id, task_id=task.id
    )
    if workspace is None:
        raise WorkspaceMissing()

    branch = submission_service.validate_branch(
        payload.branch or workspace.default_branch or "main"
    )
    try:
        async with _concurrency_guard(
            rate_limit.rate_limit_key("tasks", str(cs.id), "dispatch"),
            _RUN_CONCURRENCY_LIMIT,
        ):
            result = await submission_service.run_actions_tests(
                runner=actions_runner,
                workspace=workspace,
                branch=branch,
                workflow_inputs=payload.workflowInputs,
            )
    except GithubError as exc:
        logger.error(
            "github_run_failed",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "status_code": getattr(exc, "status_code", None),
            },
        )
        raise map_github_error(exc) from exc
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception(
            "github_run_unhandled",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
            },
        )
        raise ApiError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
            error_code="GITHUB_UNAVAILABLE",
            retryable=True,
        ) from exc

    await submission_service.record_run_result(db, workspace, result)

    return RunTestsResponse(
        status=result.status,
        passed=result.passed,
        failed=result.failed,
        total=result.total,
        stdout=result.stdout,
        stderr=result.stderr,
        timeout=result.conclusion == "timed_out",
        runId=result.run_id,
        conclusion=result.conclusion,
        workflowUrl=result.html_url,
        commitSha=result.head_sha,
        pollAfterMs=result.poll_after_ms,
    )


@router.get(
    "/{task_id}/run/{run_id}",
    response_model=RunTestsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_run_result(
    task_id: Annotated[int, Path(..., ge=1)],
    run_id: Annotated[int, Path(..., ge=1)],
    db: Annotated[AsyncSession, Depends(get_session)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
) -> RunTestsResponse:
    """Fetch a previously-dispatched workflow run result for polling."""
    cs = candidate_session
    _rate_limit_or_429(cs.id, "poll")
    if rate_limit.rate_limit_enabled():
        rate_limit.limiter.throttle(
            rate_limit.rate_limit_key("tasks", str(cs.id), "poll", str(run_id)),
            _POLL_MIN_INTERVAL_SECONDS,
        )
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    submission_service.validate_run_allowed(task)

    workspace = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=cs.id, task_id=task.id
    )
    if workspace is None:
        raise WorkspaceMissing()

    try:
        async with _concurrency_guard(
            rate_limit.rate_limit_key("tasks", str(cs.id), "fetch"),
            _RUN_CONCURRENCY_LIMIT,
        ):
            result = await actions_runner.fetch_run_result(
                repo_full_name=workspace.repo_full_name, run_id=run_id
            )
    except GithubError as exc:
        logger.error(
            "github_run_fetch_failed",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "status_code": getattr(exc, "status_code", None),
            },
        )
        raise map_github_error(exc) from exc

    await submission_service.record_run_result(db, workspace, result)

    return RunTestsResponse(
        status=result.status,
        passed=result.passed,
        failed=result.failed,
        total=result.total,
        stdout=result.stdout,
        stderr=result.stderr,
        timeout=result.conclusion == "timed_out",
        runId=result.run_id,
        conclusion=result.conclusion,
        workflowUrl=result.html_url,
        commitSha=result.head_sha,
        pollAfterMs=result.poll_after_ms,
    )


@router.post(
    "/{task_id}/submit",
    response_model=SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: SubmissionCreateRequest,
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
) -> SubmissionCreateResponse:
    """Submit a task for a candidate session using GitHub Actions results."""
    cs = candidate_session
    _rate_limit_or_429(cs.id, "submit")

    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    await submission_service.ensure_not_duplicate(db, cs.id, task_id)

    current_task = await _compute_current_task(db, cs)
    submission_service.ensure_in_order(current_task, task_id)
    submission_service.validate_submission_payload(task, payload)

    now = datetime.now(UTC)
    actions_result = None
    diff_summary_json = None
    workspace = None

    if submission_service.is_code_task(task):
        workspace = await submission_service.workspace_repo.get_by_session_and_task(
            db, candidate_session_id=cs.id, task_id=task.id
        )
        if workspace is None:
            raise WorkspaceMissing()
        branch = submission_service.validate_branch(
            getattr(payload, "branch", None) or workspace.default_branch or "main"
        )
        try:
            actions_result = await submission_service.run_actions_tests(
                runner=actions_runner,
                workspace=workspace,
                branch=branch,
                workflow_inputs=getattr(payload, "workflowInputs", None),
            )
            await submission_service.record_run_result(db, workspace, actions_result)
            if actions_result.head_sha:
                base_sha = workspace.base_template_sha or branch
                compare = await github_client.get_compare(
                    workspace.repo_full_name, base_sha, actions_result.head_sha
                )
                diff_summary_json = json.dumps(
                    submission_service.summarize_diff(
                        compare, base=base_sha, head=actions_result.head_sha
                    ),
                    ensure_ascii=False,
                )
        except GithubError as exc:
            logger.error(
                "github_submit_failed",
                extra={
                    "task_id": task.id,
                    "candidate_session_id": cs.id,
                    "status_code": getattr(exc, "status_code", None),
                },
            )
            raise map_github_error(exc) from exc
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception(
                "github_submit_unhandled",
                extra={
                    "task_id": task.id,
                    "candidate_session_id": cs.id,
                },
            )
            raise ApiError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub unavailable. Please try again.",
                error_code="GITHUB_UNAVAILABLE",
                retryable=True,
            ) from exc

    sub = await submission_service.create_submission(
        db,
        cs,
        task,
        payload,
        now=now,
        actions_result=actions_result,
        workspace=workspace,
        diff_summary_json=diff_summary_json,
    )

    completed, total, is_complete = await submission_service.progress_after_submission(
        db, cs, now=now
    )

    return SubmissionCreateResponse(
        submissionId=sub.id,
        taskId=task.id,
        candidateSessionId=cs.id,
        submittedAt=sub.submitted_at,
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )
