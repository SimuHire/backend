from __future__ import annotations

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.repo_fetch import fetch_repo_and_branch
from app.domains.github_native.template_health.schemas import WORKFLOW_DIR, TemplateHealthChecks
from app.domains.github_native.template_health.workflow_eval import validate_workflow


async def run_static_checks(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_file: str,
    checks: TemplateHealthChecks,
    errors: list[str],
) -> str | None:
    default_branch = await fetch_repo_and_branch(
        github_client, repo_full_name, checks, errors
    )
    if default_branch:
        workflow_path = f"{WORKFLOW_DIR}/{workflow_file}"
        await validate_workflow(
            github_client,
            repo_full_name=repo_full_name,
            workflow_path=workflow_path,
            default_branch=default_branch,
            checks=checks,
            errors=errors,
        )
    return default_branch
