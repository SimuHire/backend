from __future__ import annotations

from app.core.brand import TEST_ARTIFACT_NAMESPACE
from app.integrations.github.artifacts import PREFERRED_ARTIFACT_NAMES


def _workflow_contract_checks(content: str) -> dict[str, bool]:
    text = content.lower()
    has_upload_artifact = "actions/upload-artifact" in text
    has_artifact_name = any(name.lower() in text for name in PREFERRED_ARTIFACT_NAMES)
    has_test_results_json = f"{TEST_ARTIFACT_NAMESPACE}.json" in text
    return {
        "workflowHasUploadArtifact": has_upload_artifact,
        "workflowHasArtifactName": has_artifact_name,
        "workflowHasTestResultsJson": has_test_results_json,
    }


def workflow_contract_errors(content: str) -> tuple[list[str], dict[str, bool]]:
    checks = _workflow_contract_checks(content)
    errors: list[str] = []
    if not checks["workflowHasUploadArtifact"]:
        errors.append("workflow_missing_upload_artifact")
    if not checks["workflowHasArtifactName"]:
        errors.append("workflow_missing_artifact_name")
    if not checks["workflowHasTestResultsJson"]:
        errors.append("workflow_missing_test_results_json")
    return errors, checks
