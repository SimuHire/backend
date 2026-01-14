from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Submission, Task
from app.domains.candidate_sessions import service as cs_service
from app.domains.github_native.actions_runner import (
    ActionsRunResult,
    GithubActionsRunner,
)
from app.domains.github_native.client import GithubClient, GithubError
from app.domains.github_native.workspaces import repository as workspace_repo
from app.domains.github_native.workspaces.workspace import Workspace
from app.domains.submissions import repository as submissions_repo
from app.domains.submissions.exceptions import (
    SimulationComplete,
    SubmissionConflict,
    SubmissionOrderError,
)
from app.domains.tasks import repository as tasks_repo

TEXT_TASK_TYPES = {"design", "documentation", "handoff"}
CODE_TASK_TYPES = {"code", "debug"}
_GITHUB_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def is_code_task(task: Task) -> bool:
    """Return True if the task requires code (code/debug)."""
    return (task.type or "").lower() in CODE_TASK_TYPES


async def load_task_or_404(db: AsyncSession, task_id: int) -> Task:
    """Fetch a task by id or raise 404."""
    task = await tasks_repo.get_by_id(db, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


def ensure_task_belongs(task: Task, candidate_session: CandidateSession) -> None:
    """Ensure the task is part of the candidate's simulation."""
    if task.simulation_id != candidate_session.simulation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )


async def ensure_not_duplicate(
    db: AsyncSession, candidate_session_id: int, task_id: int
) -> None:
    """Guard against duplicate submissions for a task."""
    if await submissions_repo.find_duplicate(db, candidate_session_id, task_id):
        raise SubmissionConflict()


def ensure_in_order(current_task: Task | None, target_task_id: int) -> None:
    """Verify the submission is for the current task in sequence."""
    if current_task is None:
        raise SimulationComplete()
    if current_task.id != target_task_id:
        raise SubmissionOrderError()


def validate_submission_payload(task: Task, payload) -> None:
    """Validate submission payload for non-code tasks."""
    task_type = (task.type or "").lower()
    if task_type in TEXT_TASK_TYPES:
        if not payload.contentText or not payload.contentText.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="contentText is required",
            )
    elif task_type in CODE_TASK_TYPES:
        # Code tasks are GitHub-native; no payload validation required.
        return
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unknown task type",
        )


def validate_run_allowed(task: Task) -> None:
    """Run tests only applies to code/debug tasks."""
    if not is_code_task(task):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run tests is only available for code tasks",
        )


def build_repo_name(
    *,
    prefix: str,
    candidate_session: CandidateSession,
    task: Task,
) -> str:
    """Construct a deterministic repo name for a workspace."""
    return f"{prefix}{candidate_session.id}-task{task.id}"


def validate_github_username(username: str) -> None:
    """Ensure GitHub username follows GitHub rules."""
    if not username or len(username) > 39 or not _GITHUB_USERNAME_RE.match(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub username",
        )


def validate_repo_full_name(name: str) -> None:
    """Validate owner/repo format to avoid SSRF/path traversal."""
    if not _REPO_FULL_NAME_RE.match(name or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository name",
        )


def validate_branch(branch: str | None) -> str | None:
    """Ensure branch names are safe-ish."""
    if branch is None:
        return None
    if not isinstance(branch, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name",
        )
    if (
        ".." in branch
        or "//" in branch
        or branch.startswith("/")
        or branch.endswith("/")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name",
        )
    if not _BRANCH_RE.match(branch):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch name",
        )
    return branch


async def ensure_workspace(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
) -> Workspace:
    """Fetch or create a workspace for the candidate+task."""
    if github_username:
        validate_github_username(github_username)
    existing = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=candidate_session.id, task_id=task.id
    )
    if existing:
        if github_username:
            import contextlib

            with contextlib.suppress(GithubError):
                await github_client.add_collaborator(
                    existing.repo_full_name, github_username
                )
        return existing

    template_repo = (task.template_repo or "").strip()
    if not template_repo:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task template repository is not configured",
        )
    validate_repo_full_name(template_repo)

    new_repo_name = build_repo_name(
        prefix=repo_prefix, candidate_session=candidate_session, task=task
    )
    template_owner = template_repo.split("/")[0] if "/" in template_repo else None
    generated = await github_client.generate_repo_from_template(
        template_full_name=template_repo,
        new_repo_name=new_repo_name,
        owner=template_owner or template_default_owner,
        private=True,
    )

    repo_full_name = generated.get("full_name") or ""
    default_branch = generated.get("default_branch") or generated.get("master_branch")
    repo_id = generated.get("id")
    validate_repo_full_name(repo_full_name)

    base_template_sha = None
    branch_to_fetch = default_branch or "main"
    try:
        branch_data = await github_client.get_branch(repo_full_name, branch_to_fetch)
        base_template_sha = (branch_data.get("commit") or {}).get("sha")
    except GithubError:
        base_template_sha = None

    if github_username:
        import contextlib

        with contextlib.suppress(GithubError):
            await github_client.add_collaborator(repo_full_name, github_username)

    ws = await workspace_repo.create_workspace(
        db,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        template_repo_full_name=template_repo,
        repo_full_name=repo_full_name,
        repo_id=repo_id,
        default_branch=default_branch,
        base_template_sha=base_template_sha,
        created_at=now,
    )
    return ws


async def record_run_result(
    db: AsyncSession, workspace: Workspace, result: ActionsRunResult
) -> Workspace:
    """Persist latest workflow result on the workspace."""
    workspace.last_workflow_run_id = str(result.run_id)
    workspace.last_workflow_conclusion = result.conclusion
    workspace.latest_commit_sha = result.head_sha
    workspace.last_test_summary_json = json.dumps(
        result.as_test_output, ensure_ascii=False
    )
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def create_submission(
    db: AsyncSession,
    candidate_session: CandidateSession,
    task: Task,
    payload,
    *,
    now: datetime,
    actions_result: ActionsRunResult | None = None,
    workspace: Workspace | None = None,
    diff_summary_json: str | None = None,
) -> Submission:
    """Persist a submission with conflict handling."""
    tests_passed = None
    tests_failed = None
    test_output = None
    last_run_at = None
    commit_sha = None
    workflow_run_id = None
    if actions_result is not None:
        tests_passed = actions_result.passed
        tests_failed = actions_result.failed
        test_output = json.dumps(actions_result.as_test_output, ensure_ascii=False)
        last_run_at = now
        commit_sha = actions_result.head_sha
        workflow_run_id = str(actions_result.run_id)

    sub = Submission(
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        submitted_at=now,
        content_text=payload.contentText,
        code_repo_path=workspace.repo_full_name if workspace else None,
        commit_sha=commit_sha,
        workflow_run_id=workflow_run_id,
        diff_summary_json=diff_summary_json,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        test_output=test_output,
        last_run_at=last_run_at,
    )
    db.add(sub)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SubmissionConflict() from exc
    await db.refresh(sub)
    return sub


async def progress_after_submission(
    db: AsyncSession, candidate_session: CandidateSession, *, now: datetime
) -> tuple[int, int, bool]:
    """Recompute progress and update completion status if applicable."""
    (
        _,
        _completed_task_ids,
        _current,
        completed,
        total,
        is_complete,
    ) = await cs_service.progress_snapshot(db, candidate_session)

    if is_complete and candidate_session.status != "completed":
        candidate_session.status = "completed"
        if candidate_session.completed_at is None:
            candidate_session.completed_at = now
        await db.commit()
        await db.refresh(candidate_session)

    return completed, total, is_complete


async def run_actions_tests(
    *,
    runner: GithubActionsRunner,
    workspace: Workspace,
    branch: str,
    workflow_inputs: dict[str, Any] | None,
) -> ActionsRunResult:
    """Trigger and wait for Actions workflow for a workspace."""
    return await runner.dispatch_and_wait(
        repo_full_name=workspace.repo_full_name,
        ref=branch,
        inputs=workflow_inputs or {},
    )


def summarize_diff(
    compare_payload: dict[str, Any], *, base: str | None, head: str | None
) -> dict[str, Any]:
    """Reduce GitHub compare payload into a compact summary."""
    files = []
    for f in compare_payload.get("files") or []:
        files.append(
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "changes": f.get("changes"),
                "patch": f.get("patch"),
            }
        )
    return {
        "ahead_by": compare_payload.get("ahead_by"),
        "behind_by": compare_payload.get("behind_by"),
        "total_commits": compare_payload.get("total_commits"),
        "base": base,
        "head": head,
        "files": files,
    }


def build_codespace_url(repo_full_name: str) -> str:
    """Return a Codespaces deep link to resume or create a workspace."""
    return f"https://codespaces.new/{repo_full_name}?quickstart=1"
