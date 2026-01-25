from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.exceptions import WorkspaceMissing
from app.domains.submissions.rate_limits import (
    apply_rate_limit,
    concurrency_guard,
    throttle_poll,
)


async def fetch_run_result(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
    run_id: int,
    runner: GithubActionsRunner,
):
    """Fetch a specific workflow run result for polling."""
    apply_rate_limit(candidate_session.id, "poll")
    throttle_poll(candidate_session.id, run_id)
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)
    submission_service.validate_run_allowed(task)

    workspace = await submission_service.workspace_repo.get_by_session_and_task(
        db, candidate_session_id=candidate_session.id, task_id=task.id
    )
    if workspace is None:
        raise WorkspaceMissing()
    async with concurrency_guard(candidate_session.id, "fetch"):
        return (
            task,
            workspace,
            await runner.fetch_run_result(
                repo_full_name=workspace.repo_full_name, run_id=run_id
            ),
        )
