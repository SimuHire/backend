from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.common.base import APIModel


class SubmissionCreateRequest(BaseModel):
    """Schema for creating a submission."""

    contentText: str | None = Field(default=None)
    codeBlob: str | None = Field(default=None)
    files: dict[str, str] | None = Field(default=None)


class ProgressSummary(APIModel):
    """Schema for summarizing progress."""

    completed: int
    total: int


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

    blob: str | None = None
    repoPath: str | None = None


class RecruiterTestResultsOut(APIModel):
    """Schema for recruiter test results output."""

    status: str | None = None
    passed: int | None = None
    failed: int | None = None
    total: int | None = None
    output: str | None = None


class RecruiterSubmissionDetailOut(APIModel):
    """Schema for recruiter submission details output."""

    submissionId: int
    candidateSessionId: int
    task: RecruiterTaskMetaOut
    contentText: str | None = None
    code: RecruiterCodeArtifactOut | None = None
    testResults: RecruiterTestResultsOut | None = None
    submittedAt: datetime


class RecruiterSubmissionListItemOut(APIModel):
    """Schema for recruiter submission list item output."""

    submissionId: int
    candidateSessionId: int
    taskId: int
    dayIndex: int
    type: str
    submittedAt: datetime


class RecruiterSubmissionListOut(APIModel):
    """Schema for recruiter submission list output."""

    items: list[RecruiterSubmissionListItemOut]
