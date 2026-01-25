from __future__ import annotations
from datetime import datetime

from app.domains import CandidateSession, Task
from app.domains.github_native.client import GithubClient
from app.domains.github_native.workspaces import repository as workspace_repo
from app.domains.github_native.workspaces.workspace import Workspace
from app.domains.submissions.services.workspace_repo_state import (
    add_collaborator_if_needed,
    fetch_base_template_sha,
)
from app.domains.submissions.services.workspace_template_repo import generate_template_repo


async def provision_workspace(
    db,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str | None,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
) -> Workspace:
    template_repo, repo_full_name, default_branch, repo_id = await generate_template_repo(
        github_client=github_client,
        candidate_session=candidate_session,
        task=task,
        repo_prefix=repo_prefix,
        template_default_owner=template_default_owner,
    )
    base_template_sha = await fetch_base_template_sha(
        github_client, repo_full_name, default_branch
    )
    await add_collaborator_if_needed(github_client, repo_full_name, github_username)
    return await workspace_repo.create_workspace(
        db,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        template_repo_full_name=template_repo,
        repo_full_name=repo_full_name,
        repo_id=repo_id,
        default_branch=default_branch,
        base_template_sha=base_template_sha,
        created_at=now,
    )
