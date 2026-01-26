from __future__ import annotations

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.submissions import service_candidate as submission_service
from app.integrations.github.client import GithubClient, GithubError
from app.repositories.github_native.workspaces.models import Workspace
from app.services.submissions.run_service import ActionsRunResult
from app.services.submissions.use_cases.submit_diff import build_diff_summary
from app.services.submissions.use_cases.submit_workspace import (
    fetch_workspace_and_branch,
)


async def run_code_submission(
    *,
    db: AsyncSession,
    candidate_session_id: int,
    task_id: int,
    payload,
    github_client: GithubClient,
    actions_runner,
) -> tuple[ActionsRunResult | None, str | None, Workspace | None]:
    workspace, branch = await fetch_workspace_and_branch(
        db, candidate_session_id, task_id, payload
    )
    try:
        actions_result = await submission_service.run_actions_tests(
            runner=actions_runner,
            workspace=workspace,
            branch=branch or "main",
            workflow_inputs=getattr(payload, "workflowInputs", None),
        )
        await submission_service.record_run_result(db, workspace, actions_result)
        if not actions_result.head_sha:
            return actions_result, None, workspace
        diff_summary_json = await build_diff_summary(
            github_client, workspace, branch, actions_result.head_sha
        )
        return actions_result, diff_summary_json, workspace
    except GithubError:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        raise ApiError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub unavailable. Please try again.",
            error_code="GITHUB_UNAVAILABLE",
            retryable=True,
        ) from exc
