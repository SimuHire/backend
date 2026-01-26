from __future__ import annotations

from typing import Any

from app.integrations.github.artifacts import PREFERRED_ARTIFACT_NAMES


def partition_artifacts(
    artifacts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    preferred: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not artifact or artifact.get("expired"):
            continue
        name = str(artifact.get("name") or "").lower()
        (preferred if name in PREFERRED_ARTIFACT_NAMES else others).append(artifact)
    return preferred, others
