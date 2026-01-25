from __future__ import annotations

from collections import OrderedDict

from app.domains.github_native.actions_runner.cache_artifacts import ArtifactCacheMixin
from app.domains.github_native.actions_runner.cache_runs import RunCacheMixin
from app.domains.github_native.actions_runner.models import ActionsRunResult
from app.domains.github_native.artifacts import ParsedTestResults


class ActionsCache(RunCacheMixin, ArtifactCacheMixin):
    """Shared cache for run results and artifacts with simple LRU eviction."""

    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self.run_cache: OrderedDict[tuple[str, int], ActionsRunResult] = OrderedDict()
        self.artifact_cache: OrderedDict[
            tuple[str, int, int], tuple[ParsedTestResults | None, str | None]
        ] = OrderedDict()
        self.artifact_list_cache: OrderedDict[
            tuple[str, int], list[dict]
        ] = OrderedDict()
        self.poll_attempts: dict[tuple[str, int], int] = {}
