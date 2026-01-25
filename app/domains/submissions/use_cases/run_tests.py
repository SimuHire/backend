from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.exceptions import WorkspaceMissing
from app.domains.submissions.rate_limits import apply_rate_limit, concurrency_guard


async def run_task_tests(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
    runner: GithubActionsRunner,
    branch: str | None,
    workflow_inputs: dict | None,
):
    """Dispatch workflow run for the task and return result."""
    apply_rate_limit(candidate_session.id, "run")
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)
    submission_service.validate_run_allowed(task)

    workspace = await submission_service.workspace_repo.get_by_session_and_task(
        db, candidate_session_id=candidate_session.id, task_id=task.id
    )
    if workspace is None:
        raise WorkspaceMissing()
    branch_to_use = submission_service.validate_branch(
        branch or workspace.default_branch or "main"
    )
    async with concurrency_guard(candidate_session.id, "dispatch"):
        return (
            task,
            workspace,
            await submission_service.run_actions_tests(
                runner=runner,
                workspace=workspace,
                branch=branch_to_use or "main",
                workflow_inputs=workflow_inputs,
            ),
        )
