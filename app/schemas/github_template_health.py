from __future__ import annotations

from typing import Literal

from app.domains.common.base import APIModel

WORKFLOW_DIR = ".github/workflows"
LEGACY_ARTIFACT_NAME = "simuhire-test-results"
RunMode = Literal["static", "live"]


class TemplateHealthChecks(APIModel):
    """Per-template health check details."""

    repoReachable: bool = False
    defaultBranch: str | None = None
    defaultBranchUsable: bool = False
    workflowFileExists: bool = False
    workflowHasUploadArtifact: bool = False
    workflowHasArtifactName: bool = False
    workflowHasTestResultsJson: bool = False


class TemplateHealthItem(APIModel):
    """Health status for a single template repo."""

    templateKey: str
    repoFullName: str
    workflowFile: str
    defaultBranch: str | None
    ok: bool
    errors: list[str]
    checks: TemplateHealthChecks
    mode: RunMode | None = None
    workflowRunId: int | None = None
    workflowConclusion: str | None = None
    artifactNameFound: str | None = None


class TemplateHealthResponse(APIModel):
    """Aggregate health status for all templates."""

    ok: bool
    templates: list[TemplateHealthItem]
    mode: RunMode | None = None
