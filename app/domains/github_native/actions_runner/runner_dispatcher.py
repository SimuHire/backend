from __future__ import annotations

from typing import Any

from app.domains.github_native.actions_runner.dispatch import dispatch_with_fallbacks
from app.domains.github_native.actions_runner.dispatch_loop import dispatch_and_wait
from app.domains.github_native.actions_runner.run_fetcher import fetch_run_result


class DispatchRunnerMixin:
    """Async helpers for dispatching and fetching workflow runs."""

    async def dispatch_and_wait(
        self, *, repo_full_name: str, ref: str, inputs: dict[str, Any] | None = None
    ):
        return await dispatch_and_wait(
            self, repo_full_name=repo_full_name, ref=ref, inputs=inputs
        )

    async def fetch_run_result(
        self, *, repo_full_name: str, run_id: int
    ):
        return await fetch_run_result(self, repo_full_name=repo_full_name, run_id=run_id)

    async def _dispatch_with_fallbacks(
        self, repo_full_name: str, *, ref: str, inputs: dict[str, Any] | None
    ):
        return await dispatch_with_fallbacks(
            self.client,
            self._workflow_fallbacks,
            repo_full_name=repo_full_name,
            ref=ref,
            inputs=inputs,
            preferred_workflow=self.workflow_file,
        )
