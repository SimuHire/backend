from __future__ import annotations

import contextlib

from app.domains import CandidateSession, Task
from app.integrations.github.client import GithubClient, GithubError
from app.integrations.github.workspaces import repository as workspace_repo
from app.integrations.github.workspaces.workspace import Workspace


async def ensure_existing_workspace(
    db,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str | None,
) -> Workspace | None:
    existing = await workspace_repo.get_by_session_and_task(
        db, candidate_session_id=candidate_session.id, task_id=task.id
    )
    if not existing:
        return None
    if github_username:
        with contextlib.suppress(GithubError):
            await github_client.add_collaborator(
                existing.repo_full_name, github_username
            )
    return existing
