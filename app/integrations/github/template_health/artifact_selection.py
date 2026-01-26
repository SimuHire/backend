from __future__ import annotations

from app.core.brand import TEST_ARTIFACT_NAMESPACE
from app.integrations.github.template_health.schemas import LEGACY_ARTIFACT_NAME


def select_artifacts(artifacts):
    tenon_artifact = legacy_artifact = None
    artifact_name_found = None
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
    return tenon_artifact, legacy_artifact, artifact_name_found
