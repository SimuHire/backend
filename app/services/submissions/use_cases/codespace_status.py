from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.codespace_urls import ensure_canonical_workspace_url
from app.domains.submissions.exceptions import WorkspaceMissing


async def codespace_status(
    db: AsyncSession, *, candidate_session: CandidateSession, task_id: int
):
    """Return Codespace/workflow status for a candidate task."""
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)

    workspace = await submission_service.workspace_repo.get_by_session_and_task(
        db, candidate_session_id=candidate_session.id, task_id=task.id
    )
    if workspace is None:
        raise WorkspaceMissing(detail="Workspace not initialized", status_code=404)
    last_test_summary = None
    if workspace.last_test_summary_json:
        try:
            last_test_summary = json.loads(workspace.last_test_summary_json)
        except ValueError:
            last_test_summary = None
    if not workspace.repo_full_name:
        raise WorkspaceMissing(status_code=409)
    codespace_url = await ensure_canonical_workspace_url(db, workspace)
    return workspace, last_test_summary, codespace_url, task
