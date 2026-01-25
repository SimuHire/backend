from __future__ import annotations

from app.domains.github_native.template_health.item_builder import build_item
from app.domains.github_native.template_health.live_result import LiveCheckResult
from app.domains.github_native.template_health.schemas import (
    RunMode,
    TemplateHealthChecks,
)


def build_repo_result(
    template_key: str,
    repo_full_name: str,
    workflow_file: str,
    checks: TemplateHealthChecks,
    errors: list[str],
    mode: RunMode,
    default_branch: str | None,
    live_result: LiveCheckResult | None,
):
    return build_item(
        template_key,
        repo_full_name,
        workflow_file,
        checks,
        errors,
        mode,
        default_branch=default_branch,
        workflow_run_id=live_result.workflow_run_id if live_result else None,
        workflow_conclusion=live_result.workflow_conclusion if live_result else None,
        artifact_name_found=live_result.artifact_name_found if live_result else None,
    )
