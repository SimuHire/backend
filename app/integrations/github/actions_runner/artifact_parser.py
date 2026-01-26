from __future__ import annotations

from app.integrations.github.actions_runner.cache import ActionsCache
from app.integrations.github.artifacts import (
    ParsedTestResults,
    parse_test_results_zip,
)
from app.integrations.github.client import GithubClient, GithubError


async def parse_first_artifact(
    client: GithubClient,
    cache: ActionsCache,
    repo_full_name: str,
    run_id: int,
    artifacts: list[dict],
) -> tuple[ParsedTestResults | None, str | None]:
    found = False
    last_error: str | None = None
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if not artifact_id:
            continue
        found = True
        cache_key = (repo_full_name, run_id, int(artifact_id))
        cached = cache.artifact_cache.get(cache_key)
        if cached:
            parsed_cached, cached_error = cached
            if parsed_cached or cached_error:
                return parsed_cached, cached_error
        try:
            content = await client.download_artifact_zip(
                repo_full_name, int(artifact_id)
            )
        except GithubError:
            last_error = "artifact_download_failed"
            continue
        parsed = parse_test_results_zip(content)
        error = None if parsed else "artifact_corrupt"
        cache.cache_artifact_result(cache_key, parsed, error)
        if parsed:
            return parsed, None
        last_error = error
    if found:
        return None, last_error or "artifact_unavailable"
    return None, None
