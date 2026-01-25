from __future__ import annotations

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.live_check import _run_live_check
from app.domains.github_native.template_health.live_result import LiveCheckResult


async def run_live_checks(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    timeout_seconds: int,
) -> LiveCheckResult:
    return await _run_live_check(
        github_client,
        repo_full_name=repo_full_name,
        workflow_file=workflow_file,
        default_branch=default_branch,
        timeout_seconds=timeout_seconds,
    )
