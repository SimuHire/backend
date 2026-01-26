from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains import CandidateSession
from app.integrations.github.client import GithubClient
from app.services.submissions import service_candidate as submission_service
from app.services.submissions.codespace_urls import ensure_canonical_workspace_url
from app.services.submissions.rate_limits import apply_rate_limit
from app.services.submissions.use_cases.codespace_validations import (
    validate_codespace_request,
)


async def init_codespace(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
    github_client: GithubClient,
    github_username: str,
    repo_prefix: str,
    template_owner: str | None,
    now: datetime | None = None,
):
    apply_rate_limit(candidate_session.id, "init")
    task = await validate_codespace_request(db, candidate_session, task_id)
    workspace = await submission_service.ensure_workspace(
        db,
        candidate_session=candidate_session,
        task=task,
        github_client=github_client,
        github_username=github_username,
        repo_prefix=repo_prefix,
        template_default_owner=template_owner,
        now=now or datetime.now(UTC),
    )
    if not workspace.repo_full_name:
        raise ApiError(status_code=409, detail="Workspace repo not provisioned yet. Please try again.", error_code="WORKSPACE_NOT_READY", retryable=True)
    codespace_url = await ensure_canonical_workspace_url(db, workspace)
    return (workspace, submission_service.build_codespace_url(workspace.repo_full_name), codespace_url, task)

__all__ = ["init_codespace"]
