from __future__ import annotations
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Submission, Task
from app.domains.github_native.actions_runner import ActionsRunResult
from app.domains.github_native.workspaces.workspace import Workspace
from app.domains.submissions.exceptions import SubmissionConflict
from app.domains.submissions.services.submission_actions import derive_actions_metadata
from app.domains.submissions.services.submission_builder import build_submission


async def create_submission(
    db: AsyncSession,
    candidate_session: CandidateSession,
    task: Task,
    payload,
    *,
    now: datetime,
    actions_result: ActionsRunResult | None = None,
    workspace: Workspace | None = None,
    diff_summary_json: str | None = None,
) -> Submission:
    """Persist a submission with conflict handling."""
    actions_meta = derive_actions_metadata(actions_result, now)
    sub = build_submission(
        candidate_session=candidate_session,
        task=task,
        payload=payload,
        now=now,
        workspace=workspace,
        diff_summary_json=diff_summary_json,
        **actions_meta,
    )
    db.add(sub)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SubmissionConflict() from exc
    await db.refresh(sub)
    return sub
