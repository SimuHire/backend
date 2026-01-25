from __future__ import annotations

from app.domains.github_native.actions_runner.artifact_list import (
    list_artifacts_with_cache,
)
from app.domains.github_native.actions_runner.artifact_parser import (
    parse_first_artifact,
)
from app.domains.github_native.actions_runner.artifact_partition import (
    partition_artifacts,
)
from app.domains.github_native.actions_runner.cache import ActionsCache
from app.domains.github_native.artifacts import ParsedTestResults
from app.domains.github_native.client import GithubClient


async def parse_artifacts(
    client: GithubClient, cache: ActionsCache, repo_full_name: str, run_id: int
) -> tuple[ParsedTestResults | None, str | None]:
    artifacts = await list_artifacts_with_cache(client, cache, repo_full_name, run_id)
    preferred, others = partition_artifacts(artifacts)
    parsed, error = await parse_first_artifact(
        client, cache, repo_full_name, run_id, preferred + others
    )
    if parsed:
        return parsed, None
    if error:
        return None, error
    return None, "artifact_missing"
