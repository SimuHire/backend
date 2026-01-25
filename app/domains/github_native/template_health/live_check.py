from __future__ import annotations

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.live_artifacts import (
    collect_artifact_status,
)
from app.domains.github_native.template_health.live_dispatch import dispatch_and_poll
from app.domains.github_native.template_health.live_result import LiveCheckResult


async def _run_live_check(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    timeout_seconds: int,
) -> LiveCheckResult:
    errors, workflow_run_id, workflow_conclusion = await dispatch_and_poll(
        github_client,
        repo_full_name=repo_full_name,
        workflow_file=workflow_file,
        default_branch=default_branch,
        timeout_seconds=timeout_seconds,
    )
    if errors or workflow_run_id is None:
        return LiveCheckResult(
            errors or ["workflow_run_timeout"],
            workflow_run_id,
            workflow_conclusion,
            None,
        )

    artifact_errors, artifact_name_found = await collect_artifact_status(
        github_client,
        repo_full_name=repo_full_name,
        workflow_run_id=workflow_run_id,
    )
    if workflow_conclusion and workflow_conclusion != "success":
        artifact_errors.append("workflow_run_not_success")

    return LiveCheckResult(
        artifact_errors,
        workflow_run_id,
        workflow_conclusion,
        artifact_name_found,
    )
