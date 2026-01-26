from __future__ import annotations

from app.integrations.github import GithubClient, GithubError
from app.integrations.github.template_health.artifacts import (
    _extract_test_results_json,
    _validate_test_results_schema,
)
from app.integrations.github.template_health.classify import _classify_github_error


async def validate_artifact_payload(
    github_client: GithubClient, *, repo_full_name: str, artifact_id: int
) -> str | None:
    try:
        zip_content = await github_client.download_artifact_zip(
            repo_full_name, artifact_id
        )
    except GithubError as exc:
        return _classify_github_error(exc) or "artifact_missing"

    payload = _extract_test_results_json(zip_content)
    if payload is None:
        return "artifact_zip_missing_test_results_json"
    if not _validate_test_results_schema(payload):
        return "test_results_json_invalid_schema"
    return None
