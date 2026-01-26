from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.exceptions import WorkspaceMissing
from app.repositories.github_native.workspaces.models import Workspace


async def fetch_workspace_and_branch(
    db: AsyncSession, candidate_session_id: int, task_id: int, payload
) -> tuple[Workspace, str]:
    workspace = await submission_service.workspace_repo.get_by_session_and_task(
        db, candidate_session_id=candidate_session_id, task_id=task_id
    )
    if workspace is None:  # pragma: no cover - defensive guard
        raise WorkspaceMissing()
    branch = submission_service.validate_branch(
        getattr(payload, "branch", None) or workspace.default_branch or "main"
    )
    return workspace, branch
