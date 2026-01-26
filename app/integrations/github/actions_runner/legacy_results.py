from __future__ import annotations

from app.integrations.github.actions_runner.artifacts import parse_artifacts
from app.integrations.github.actions_runner.backoff import apply_backoff
from app.integrations.github.actions_runner.normalize import normalize_run
from app.integrations.github.actions_runner.result_builder import build_result
from app.integrations.github.actions_runner.runs import (
    is_dispatched_run,
    run_cache_key,
)


class LegacyResultMixin:
    """Legacy helpers preserved for tests and compatibility."""

    def _normalize_run(self, run, *, timed_out: bool = False, running: bool = False):
        return normalize_run(run, timed_out=timed_out, running=running)

    def _is_dispatched_run(self, run, dispatch_started_at):
        return is_dispatched_run(run, dispatch_started_at)

    @staticmethod
    def _run_cache_key(repo_full_name: str, run_id: int) -> tuple[str, int]:
        return run_cache_key(repo_full_name, run_id)

    def _apply_backoff(self, key, result):
        apply_backoff(self.cache, key, result, self.poll_interval_seconds)

    async def _parse_artifacts(self, repo_full_name: str, run_id: int):
        return await parse_artifacts(self.client, self.cache, repo_full_name, run_id)

    async def _build_result(self, repo_full_name: str, run):
        return await build_result(self, repo_full_name, run)
