from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.settings import settings
from app.integrations.github import GithubClient
from app.integrations.github.actions_runner import GithubActionsRunner


@lru_cache(maxsize=1)
def _github_client_singleton() -> GithubClient:
    return GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )


def get_github_client() -> GithubClient:
    """Default GitHub client dependency."""
    return _github_client_singleton()


@lru_cache(maxsize=1)
def _actions_runner_singleton() -> GithubActionsRunner:
    return GithubActionsRunner(
        _github_client_singleton(),
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        poll_interval_seconds=2.0,
        max_poll_seconds=90.0,
    )


def get_actions_runner(
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> GithubActionsRunner:
    """Actions runner dependency with configured workflow file."""
    if github_client is not _github_client_singleton():
        return GithubActionsRunner(
            github_client,
            workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
            poll_interval_seconds=2.0,
            max_poll_seconds=90.0,
        )
    return _actions_runner_singleton()
