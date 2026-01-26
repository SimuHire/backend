from __future__ import annotations

from app.integrations.github.actions_runner.models import ActionsRunResult


class RunCacheMixin:
    """Cache helpers for workflow run results."""

    run_cache: dict
    poll_attempts: dict
    max_entries: int

    def cache_run(self, key: tuple[str, int], result: ActionsRunResult) -> None:
        self.run_cache[key] = result
        self.run_cache.move_to_end(key)
        if len(self.run_cache) > self.max_entries:
            evicted, _ = self.run_cache.popitem(last=False)
            self.poll_attempts.pop(evicted, None)
        if self.is_terminal(result):
            self.poll_attempts.pop(key, None)

    @staticmethod
    def is_terminal(result: ActionsRunResult) -> bool:
        if result.conclusion:
            return True
        return result.status in {"passed", "failed", "cancelled", "timed_out", "error"}
