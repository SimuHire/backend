from __future__ import annotations

# NOTE: This orchestrator stays together (>50 LOC) to keep the codespace init flow coherent across DB and GitHub calls.
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service
from app.domains.github_native.client import GithubClient
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.codespace_urls import ensure_canonical_workspace_url
from app.domains.submissions.rate_limits import apply_rate_limit
from app.infra.errors import ApiError


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
    """Orchestrate workspace provisioning for a candidate task."""
    apply_rate_limit(candidate_session.id, "init")
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)

    _, _, current, *_ = await cs_service.progress_snapshot(db, candidate_session)
    submission_service.ensure_in_order(current, task_id)
    submission_service.validate_run_allowed(task)

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
        raise ApiError(
            status_code=409,
            detail="Workspace repo not provisioned yet. Please try again.",
            error_code="WORKSPACE_NOT_READY",
            retryable=True,
        )
    codespace_url = await ensure_canonical_workspace_url(db, workspace)
    return (
        workspace,
        submission_service.build_codespace_url(workspace.repo_full_name),
        codespace_url,
        task,
    )
