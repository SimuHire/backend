from __future__ import annotations

from app.integrations.github.artifacts import ParsedTestResults


class ArtifactCacheMixin:
    """Cache helpers for artifact lists and parsed content."""

    artifact_cache: dict
    artifact_list_cache: dict
    max_entries: int

    def cache_artifact_result(
        self,
        key: tuple[str, int, int],
        parsed: ParsedTestResults | None,
        error: str | None,
    ) -> None:
        self.artifact_cache[key] = (parsed, error)
        self.artifact_cache.move_to_end(key)
        if len(self.artifact_cache) > self.max_entries:
            self.artifact_cache.popitem(last=False)

    def cache_artifact_list(self, key: tuple[str, int], artifacts: list[dict]) -> None:
        self.artifact_list_cache[key] = artifacts
        self.artifact_list_cache.move_to_end(key)
        if len(self.artifact_list_cache) > self.max_entries:
            evicted, _ = self.artifact_list_cache.popitem(last=False)
            to_remove = [
                cache_key
                for cache_key in list(self.artifact_cache)
                if cache_key[0] == evicted[0] and cache_key[1] == evicted[1]
            ]
            for cache_key in to_remove:
                self.artifact_cache.pop(cache_key, None)
