from __future__ import annotations

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.repo_live import run_live_checks
from app.domains.github_native.template_health.repo_result import build_repo_result
from app.domains.github_native.template_health.repo_static import run_static_checks
from app.domains.github_native.template_health.schemas import (
    RunMode,
    TemplateHealthChecks,
    TemplateHealthItem,
)


async def check_template_repo(
    github_client: GithubClient,
    *,
    template_key: str,
    repo_full_name: str,
    workflow_file: str,
    mode: RunMode,
    timeout_seconds: int,
) -> TemplateHealthItem:
    errors: list[str] = []
    checks = TemplateHealthChecks()
    default_branch = await run_static_checks(
        github_client,
        repo_full_name=repo_full_name,
        workflow_file=workflow_file,
        checks=checks,
        errors=errors,
    )
    live_result = None
    if mode == "live" and not errors and default_branch:
        live = await run_live_checks(
            github_client,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(live.errors)
        live_result = live
    return build_repo_result(
        template_key,
        repo_full_name,
        workflow_file,
        checks,
        errors,
        mode,
        default_branch,
        live_result,
    )
