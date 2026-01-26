from __future__ import annotations

from app.integrations.github import GithubClient, GithubError
from app.integrations.github.template_health.artifact_selection import (
    select_artifacts,
)
from app.integrations.github.template_health.artifact_validation import (
    validate_artifact_payload,
)
from app.integrations.github.template_health.classify import _classify_github_error


async def collect_artifact_status(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_run_id: int,
) -> tuple[list[str], str | None]:
    errors: list[str] = []
    try:
        artifacts = await github_client.list_artifacts(repo_full_name, workflow_run_id)
    except GithubError as exc:
        return [_classify_github_error(exc) or "artifact_missing"], None

    tenon_artifact, legacy_artifact, artifact_name_found = select_artifacts(artifacts)
    if tenon_artifact is None:
        errors.append(
            "artifact_legacy_name_simuhire" if legacy_artifact else "artifact_missing"
        )
        return errors, artifact_name_found

    artifact_id = tenon_artifact.get("id")
    if not artifact_id:
        errors.append("artifact_missing")
        return errors, artifact_name_found

    error = await validate_artifact_payload(
        github_client, repo_full_name=repo_full_name, artifact_id=int(artifact_id)
    )
    if error:
        errors.append(error)
    return errors, artifact_name_found
