from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_utils import map_github_error
from app.core.settings import settings
from app.domains import CandidateSession
from app.domains.submissions.schemas import CodespaceInitRequest, CodespaceInitResponse
from app.domains.submissions.use_cases.codespace_init import init_codespace
from app.integrations.github import GithubClient, GithubError


async def handle_codespace_init(
    task_id: int,
    payload: CodespaceInitRequest,
    candidate_session: CandidateSession,
    db: AsyncSession,
    github_client: GithubClient,
) -> CodespaceInitResponse:
    try:
        workspace, _, codespace_url, _ = await init_codespace(
            db,
            candidate_session=candidate_session,
            task_id=task_id,
            github_client=github_client,
            github_username=payload.githubUsername,
            repo_prefix=settings.github.GITHUB_REPO_PREFIX,
            template_owner=settings.github.GITHUB_TEMPLATE_OWNER
            or settings.github.GITHUB_ORG,
            now=datetime.now(UTC),
        )
    except GithubError as exc:
        raise map_github_error(exc) from exc

    return CodespaceInitResponse(
        repoFullName=workspace.repo_full_name,
        repoUrl=f"https://github.com/{workspace.repo_full_name}",
        codespaceUrl=codespace_url,
        defaultBranch=workspace.default_branch,
        workspaceId=workspace.id,
    )
