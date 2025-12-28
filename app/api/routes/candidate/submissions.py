import json
import logging
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.domain import CandidateSession, Task
from app.domain.candidate_sessions import service as cs_service
from app.domain.submissions import service_candidate as submission_service
from app.domain.submissions.schemas import (
    CodespaceInitRequest,
    CodespaceInitResponse,
    CodespaceStatusResponse,
    ProgressSummary,
    RunTestsRequest,
    RunTestsResponse,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)
from app.domain.workspaces import repository as workspace_repo
from app.services.github import GithubClient, GithubError
from app.services.github.actions import GithubActionsRunner

router = APIRouter()

logger = logging.getLogger(__name__)

_RATE_LIMIT_STORE: dict[tuple[int, str], list[float]] = {}
_RATE_LIMIT_RULE = {
    "init": (20, 30.0),  # minimal in-memory limit for YC demo
    "run": (20, 30.0),
    "submit": (10, 30.0),
}


def _rate_limit_or_429(candidate_session_id: int, action: str) -> None:
    """Apply a single rate-limit bucket for the given action."""
    env = getattr(settings, "ENV", "local").lower()
    if env != "prod":
        return
    limit, window = _RATE_LIMIT_RULE.get(action, (5, 30.0))
    now = time.monotonic()
    key = (candidate_session_id, action)
    entries = [t for t in _RATE_LIMIT_STORE.get(key, []) if now - t <= window]
    if len(entries) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
        )
    entries.append(now)
    _RATE_LIMIT_STORE[key] = entries


async def _load_candidate_session_or_404(
    db: AsyncSession,
    candidate_session_id: int,
    token: str,
) -> CandidateSession:
    return await cs_service.fetch_by_id_and_token(
        db, candidate_session_id, token, now=datetime.now(UTC)
    )


async def _compute_current_task(db: AsyncSession, cs: CandidateSession) -> Task | None:
    tasks, _, current, *_ = await cs_service.progress_snapshot(db, cs)
    return current


def get_github_client() -> GithubClient:
    """Default GitHub client dependency."""
    return GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )


def get_actions_runner(
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> GithubActionsRunner:
    """Actions runner dependency with configured workflow file."""
    return GithubActionsRunner(
        github_client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        poll_interval_seconds=2.0,
        max_poll_seconds=90.0,
    )


@router.post(
    "/{task_id}/codespace/init",
    response_model=CodespaceInitResponse,
    status_code=status.HTTP_200_OK,
)
async def init_codespace(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: CodespaceInitRequest,
    x_candidate_token: Annotated[str, Header(..., alias="x-candidate-token")],
    x_candidate_session_id: Annotated[int, Header(..., alias="x-candidate-session-id")],
    db: Annotated[AsyncSession, Depends(get_session)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> CodespaceInitResponse:
    """Provision or return a GitHub workspace for the candidate task."""
    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )
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
            f"github_workspace_create_failed {exc}",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
        ) from exc

    codespace_url = submission_service.build_codespace_url(workspace.repo_full_name)
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
    x_candidate_token: Annotated[str, Header(..., alias="x-candidate-token")],
    x_candidate_session_id: Annotated[int, Header(..., alias="x-candidate-session-id")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CodespaceStatusResponse:
    """Return current workspace status for a task."""
    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)

    workspace = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=cs.id, task_id=task.id
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not initialized"
        )

    last_test_summary = None
    if workspace.last_test_summary_json:
        try:
            last_test_summary = json.loads(workspace.last_test_summary_json)
        except ValueError:
            last_test_summary = None

    return CodespaceStatusResponse(
        repoFullName=workspace.repo_full_name,
        repoUrl=f"https://github.com/{workspace.repo_full_name}",
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
    x_candidate_token: Annotated[str | None, Header(alias="x-candidate-token")] = None,
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id")
    ] = None,
) -> RunTestsResponse:
    """Trigger GitHub Actions tests for a code/debug task."""
    if not x_candidate_token or x_candidate_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
        )

    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )
    _rate_limit_or_429(cs.id, "run")
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    submission_service.validate_run_allowed(task)

    workspace = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=cs.id, task_id=task.id
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace not initialized. Call /codespace/init first.",
        )

    branch = submission_service.validate_branch(
        payload.branch or workspace.default_branch or "main"
    )
    try:
        result = await submission_service.run_actions_tests(
            runner=actions_runner,
            workspace=workspace,
            branch=branch,
            workflow_inputs=payload.workflowInputs,
        )
    except GithubError as exc:
        logger.error(
            f"github_run_failed {exc}",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
        ) from exc
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception(
            "github_run_unhandled",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
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
    x_candidate_token: Annotated[str | None, Header(alias="x-candidate-token")] = None,
    x_candidate_session_id: Annotated[
        int | None, Header(alias="x-candidate-session-id")
    ] = None,
) -> RunTestsResponse:
    """Fetch a previously-dispatched workflow run result for polling."""
    if not x_candidate_token or x_candidate_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing candidate session headers",
        )

    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )
    _rate_limit_or_429(cs.id, "run")
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, cs)
    submission_service.validate_run_allowed(task)

    workspace = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=cs.id, task_id=task.id
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace not initialized. Call /codespace/init first.",
        )

    try:
        result = await actions_runner.fetch_run_result(
            repo_full_name=workspace.repo_full_name, run_id=run_id
        )
    except GithubError as exc:
        logger.error(
            "github_run_fetch_failed",
            extra={
                "task_id": task.id,
                "candidate_session_id": cs.id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
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
    )


@router.post(
    "/{task_id}/submit",
    response_model=SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: SubmissionCreateRequest,
    x_candidate_token: Annotated[str, Header(..., alias="x-candidate-token")],
    x_candidate_session_id: Annotated[int, Header(..., alias="x-candidate-session-id")],
    db: Annotated[AsyncSession, Depends(get_session)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
    actions_runner: Annotated[GithubActionsRunner, Depends(get_actions_runner)],
) -> SubmissionCreateResponse:
    """Submit a task for a candidate session using GitHub Actions results."""
    cs = await _load_candidate_session_or_404(
        db, x_candidate_session_id, x_candidate_token
    )
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workspace not initialized. Call /codespace/init first.",
            )
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
                    "error": str(exc),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub unavailable. Please try again.",
            ) from exc
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception(
                "github_submit_unhandled",
                extra={
                    "task_id": task.id,
                    "candidate_session_id": cs.id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub unavailable. Please try again.",
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
