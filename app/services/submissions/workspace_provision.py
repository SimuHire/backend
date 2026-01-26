from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.integrations.github.client import GithubClient
from app.repositories.github_native.workspaces.models import Workspace
from app.services.submissions.github_user import validate_github_username
from app.services.submissions.workspace_creation import provision_workspace
from app.services.submissions.workspace_existing import ensure_existing_workspace


async def ensure_workspace(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
) -> Workspace:
    """Fetch or create a workspace for the candidate+task."""
    if github_username:
        validate_github_username(github_username)

    existing = await ensure_existing_workspace(
        db,
        candidate_session=candidate_session,
        task=task,
        github_client=github_client,
        github_username=github_username,
    )
    if existing:
        return existing

    return await provision_workspace(
        db,
        candidate_session=candidate_session,
        task=task,
        github_client=github_client,
        github_username=github_username,
        repo_prefix=repo_prefix,
        template_default_owner=template_default_owner,
        now=now,
    )
