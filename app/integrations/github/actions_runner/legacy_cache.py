from __future__ import annotations


class LegacyCacheMixin:
    """Expose cache internals for tests."""

    def _cache_run_result(self, key: tuple[str, int], result):
        self.cache.cache_run(key, result)

    def _cache_artifact_result(self, key, parsed, error):
        self.cache.cache_artifact_result(key, parsed, error)

    def _cache_artifact_list(self, key, artifacts):
        self.cache.cache_artifact_list(key, artifacts)

    @property
    def _run_cache(self):
        return self.cache.run_cache

    @property
    def _artifact_cache(self):
        return self.cache.artifact_cache

    @property
    def _artifact_list_cache(self):
        return self.cache.artifact_list_cache

    @property
    def _poll_attempts(self):
        return self.cache.poll_attempts

    @property
    def _max_cache_entries(self):
        return self.cache.max_entries

    @_max_cache_entries.setter
    def _max_cache_entries(self, value: int):
        self.cache.max_entries = value
