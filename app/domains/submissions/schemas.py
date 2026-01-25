from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domains.common.base import APIModel
from app.domains.common.progress import ProgressSummary


class SubmissionCreateRequest(BaseModel):
    """Schema for creating a submission."""

    contentText: str | None = Field(default=None)
    branch: str | None = Field(default=None)
    workflowInputs: dict[str, Any] | None = Field(default=None)
    # Code tasks are GitHub-native; code payload is no longer accepted.


class RunTestsRequest(BaseModel):
    """Schema for executing GitHub Actions tests."""

    workflowInputs: dict[str, Any] | None = Field(default=None)
    branch: str | None = Field(default=None)


class RunTestsResponse(APIModel):
    """Schema for Actions run response."""

    status: str
    passed: int | None = None
    failed: int | None = None
    total: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    timeout: bool | None = None
    runId: int | None = None
    conclusion: str | None = None
    workflowUrl: str | None = None
    commitSha: str | None = None
    pollAfterMs: int | None = None


class CodespaceInitRequest(BaseModel):
    """Request to initialize a Codespace workspace."""

    githubUsername: str


class CodespaceInitResponse(APIModel):
    """Response payload for Codespace init."""

    repoFullName: str
    repoUrl: str
    codespaceUrl: str
    defaultBranch: str | None = None
    workspaceId: str


class CodespaceStatusResponse(APIModel):
    """Current status for a workspace repo."""

    repoFullName: str
    repoUrl: str
    codespaceUrl: str | None = None
    defaultBranch: str | None = None
    latestCommitSha: str | None = None
    lastWorkflowRunId: str | None = None
    lastWorkflowConclusion: str | None = None
    lastTestSummary: dict[str, Any] | None = None
    workspaceId: str


class SubmissionCreateResponse(APIModel):
    """Schema for submission creation response."""

    submissionId: int
    taskId: int
    candidateSessionId: int
    submittedAt: datetime
    progress: ProgressSummary
    isComplete: bool


class RecruiterTaskMetaOut(APIModel):
    """Schema for recruiter task metadata output."""

    taskId: int
    dayIndex: int
    type: str
    title: str | None = None
    prompt: str | None = None


class RecruiterCodeArtifactOut(APIModel):
    """Schema for recruiter code artifact output."""

    repoPath: str | None = None
    repoFullName: str | None = None
    repoUrl: str | None = None


class RecruiterTestResultsOut(APIModel):
    """Schema for recruiter test results output."""

    status: str | None = None
    passed: int | None = None
    failed: int | None = None
    total: int | None = None
    runId: int | str | None = None
    runStatus: str | None = None
    conclusion: str | None = None
    timeout: bool | None = None
    stdout: str | None = None
    stderr: str | None = None
    summary: dict[str, object] | None = None
    stdoutTruncated: bool | None = None
    stderrTruncated: bool | None = None
    artifactName: str | None = None
    artifactPresent: bool | None = None
    artifactErrorCode: str | None = None
    output: dict[str, object] | str | None = None
    lastRunAt: datetime | None = None
    workflowRunId: str | None = None
    commitSha: str | None = None
    workflowUrl: str | None = None
    commitUrl: str | None = None


class RecruiterSubmissionDetailOut(APIModel):
    """Schema for recruiter submission details output."""

    submissionId: int
    candidateSessionId: int
    task: RecruiterTaskMetaOut
    contentText: str | None = None
    code: RecruiterCodeArtifactOut | None = None
    testResults: RecruiterTestResultsOut | None = None
    diffSummary: dict[str, object] | str | None = None
    submittedAt: datetime
    workflowUrl: str | None = None
    commitUrl: str | None = None
    diffUrl: str | None = None


class RecruiterSubmissionListItemOut(APIModel):
    """Schema for recruiter submission list item output."""

    submissionId: int
    candidateSessionId: int
    taskId: int
    dayIndex: int
    type: str
    submittedAt: datetime
    repoFullName: str | None = None
    repoUrl: str | None = None
    workflowRunId: str | None = None
    commitSha: str | None = None
    workflowUrl: str | None = None
    commitUrl: str | None = None
    diffUrl: str | None = None
    diffSummary: dict[str, object] | str | None = None
    testResults: RecruiterTestResultsOut | None = None


class RecruiterSubmissionListOut(APIModel):
    """Schema for recruiter submission list output."""

    items: list[RecruiterSubmissionListItemOut]
    # Extend here if pagination is added later; keep per-item fields on the list item.
