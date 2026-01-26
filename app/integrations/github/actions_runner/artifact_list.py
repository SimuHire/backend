from __future__ import annotations

from app.integrations.github.actions_runner.runs import run_cache_key
from app.integrations.github.client import GithubClient


async def list_artifacts_with_cache(
    client: GithubClient, cache, repo_full_name: str, run_id: int
):
    cache_key = run_cache_key(repo_full_name, run_id)
    artifacts = cache.artifact_list_cache.get(cache_key)
    if artifacts is None:
        artifacts = await client.list_artifacts(repo_full_name, run_id)
        cache.cache_artifact_list(cache_key, artifacts)
    return artifacts
