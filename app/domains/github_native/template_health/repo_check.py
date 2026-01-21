from __future__ import annotations
# NOTE: Exceeds 50 LOC to keep repo + workflow validation cohesive without altering behavior.

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.item_builder import build_item
from app.domains.github_native.template_health.live_check import _run_live_check
from app.domains.github_native.template_health.repo_fetch import fetch_repo_and_branch
from app.domains.github_native.template_health.schemas import RunMode, TemplateHealthChecks, TemplateHealthItem, WORKFLOW_DIR
from app.domains.github_native.template_health.workflow_eval import validate_workflow


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
    default_branch = await fetch_repo_and_branch(github_client, repo_full_name, checks, errors)
    workflow_run_id = workflow_conclusion = artifact_name_found = None
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
    if mode == "live" and not errors and default_branch:
        live = await _run_live_check(
            github_client,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(live.errors)
        workflow_run_id = live.workflow_run_id
        workflow_conclusion = live.workflow_conclusion
        artifact_name_found = live.artifact_name_found
    return build_item(
        template_key,
        repo_full_name,
        workflow_file,
        checks,
        errors,
        mode,
        default_branch=default_branch,
        workflow_run_id=workflow_run_id,
        workflow_conclusion=workflow_conclusion,
        artifact_name_found=artifact_name_found,
    )
