from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.domains.github_native import GithubClient
from app.domains.github_native.actions_runner import GithubActionsRunner
from app.infra.config import settings


def get_github_client() -> GithubClient:
    """Default GitHub client dependency."""
    return GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )


def get_actions_runner(
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> GithubActionsRunner:
    """Actions runner dependency with configured workflow file."""
    return GithubActionsRunner(
        github_client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        poll_interval_seconds=2.0,
        max_poll_seconds=90.0,
    )
