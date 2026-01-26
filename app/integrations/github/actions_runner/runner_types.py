from __future__ import annotations

from typing import Any, Protocol

from app.integrations.github.actions_runner.cache import ActionsCache
from app.integrations.github.client import GithubClient


class RunnerContext(Protocol):
    client: GithubClient
    cache: ActionsCache
    poll_interval_seconds: float
    max_poll_seconds: float

    async def _parse_artifacts(self, repo_full_name: str, run_id: int):
        ...

    async def _dispatch_with_fallbacks(
        self, repo_full_name: str, *, ref: str, inputs: dict[str, Any] | None
    ):
        ...
