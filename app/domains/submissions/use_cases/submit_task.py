from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.github_native.client import GithubClient
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.rate_limits import apply_rate_limit
from app.domains.submissions.use_cases.submit_task_runner import run_code_submission
from app.domains.submissions.use_cases.submit_validation import validate_submission_flow


async def submit_task(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
    payload,
    github_client: GithubClient,
    actions_runner,
):
    apply_rate_limit(candidate_session.id, "submit")
    task = await validate_submission_flow(db, candidate_session, task_id, payload)
    now = datetime.now(UTC)
    actions_result = diff_summary_json = workspace = None
    if submission_service.is_code_task(task):
        actions_result, diff_summary_json, workspace = await run_code_submission(
            db=db,
            candidate_session_id=candidate_session.id,
            task_id=task.id,
            payload=payload,
            github_client=github_client,
            actions_runner=actions_runner,
        )
    submission = await submission_service.create_submission(
        db,
        candidate_session,
        task,
        payload,
        now=now,
        actions_result=actions_result,
        workspace=workspace,
        diff_summary_json=diff_summary_json,
    )
    completed, total, is_complete = await submission_service.progress_after_submission(
        db, candidate_session, now=now
    )
    return task, submission, completed, total, is_complete
