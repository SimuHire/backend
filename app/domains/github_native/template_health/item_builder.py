from __future__ import annotations

from app.domains.github_native.template_health.schemas import (
    RunMode,
    TemplateHealthChecks,
    TemplateHealthItem,
)


def build_item(
    template_key: str,
    repo_full_name: str,
    workflow_file: str,
    checks: TemplateHealthChecks,
    errors: list[str],
    mode: RunMode,
    *,
    default_branch: str | None = None,
    workflow_run_id: int | None = None,
    workflow_conclusion: str | None = None,
    artifact_name_found: str | None = None,
) -> TemplateHealthItem:
    return TemplateHealthItem(
        templateKey=template_key,
        repoFullName=repo_full_name,
        workflowFile=workflow_file,
        defaultBranch=default_branch,
        ok=len(errors) == 0,
        errors=errors,
        checks=checks,
        mode=mode,
        workflowRunId=workflow_run_id,
        workflowConclusion=workflow_conclusion,
        artifactNameFound=artifact_name_found,
    )
