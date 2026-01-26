from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_utils import map_github_error
from app.domains import CandidateSession
from app.domains.submissions.schemas import (
    ProgressSummary,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)
from app.domains.submissions.use_cases.submit_task import submit_task
from app.integrations.github import GithubClient, GithubError
from app.integrations.github.actions_runner import GithubActionsRunner


async def handle_submit_task(
    task_id: int,
    payload: SubmissionCreateRequest,
    candidate_session: CandidateSession,
    db: AsyncSession,
    github_client: GithubClient,
    actions_runner: GithubActionsRunner,
) -> SubmissionCreateResponse:
    try:
        task, submission, completed, total, is_complete = await submit_task(
            db,
            candidate_session=candidate_session,
            task_id=task_id,
            payload=payload,
            github_client=github_client,
            actions_runner=actions_runner,
        )
    except GithubError as exc:
        raise map_github_error(exc) from exc

    return SubmissionCreateResponse(
        submissionId=submission.id,
        taskId=task.id,
        candidateSessionId=candidate_session.id,
        submittedAt=submission.submitted_at,
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )
