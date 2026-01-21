from __future__ import annotations
# NOTE: Exceeds 50 LOC to keep artifact selection and validation together without changing behavior.

from app.core.brand import TEST_ARTIFACT_NAMESPACE
from app.domains.github_native import GithubClient, GithubError
from app.domains.github_native.template_health.artifacts import _extract_test_results_json, _validate_test_results_schema
from app.domains.github_native.template_health.classify import _classify_github_error
from app.domains.github_native.template_health.schemas import LEGACY_ARTIFACT_NAME


async def collect_artifact_status(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_run_id: int,
) -> tuple[list[str], str | None]:
    errors: list[str] = []; artifact_name_found = None
    try:
        artifacts = await github_client.list_artifacts(repo_full_name, workflow_run_id)
    except GithubError as exc:
        return [_classify_github_error(exc) or "artifact_missing"], None

    tenon_artifact = legacy_artifact = None
    for artifact in artifacts:
        if not artifact or artifact.get("expired"):
            continue
        name = str(artifact.get("name") or "")
        lowered = name.lower()
        if lowered == LEGACY_ARTIFACT_NAME:
            legacy_artifact = artifact
            artifact_name_found = name
        if lowered == TEST_ARTIFACT_NAMESPACE:
            tenon_artifact = artifact
            artifact_name_found = name

    if tenon_artifact is None:
        errors.append("artifact_legacy_name_simuhire" if legacy_artifact else "artifact_missing")
        return errors, artifact_name_found

    artifact_id = tenon_artifact.get("id")
    if not artifact_id:
        errors.append("artifact_missing")
        return errors, artifact_name_found

    try:
        zip_content = await github_client.download_artifact_zip(repo_full_name, int(artifact_id))
    except GithubError as exc:
        errors.append(_classify_github_error(exc) or "artifact_missing")
        return errors, artifact_name_found

    payload = _extract_test_results_json(zip_content)
    if payload is None:
        errors.append("artifact_zip_missing_test_results_json")
        return errors, artifact_name_found
    if not _validate_test_results_schema(payload):
        errors.append("test_results_json_invalid_schema")
    return errors, artifact_name_found
