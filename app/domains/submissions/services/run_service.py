from __future__ import annotations

from typing import Any

from app.domains.github_native.actions_runner import (
    ActionsRunResult,
    GithubActionsRunner,
)
from app.domains.github_native.workspaces.workspace import Workspace


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
