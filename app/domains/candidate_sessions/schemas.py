from datetime import datetime

from pydantic import EmailStr, Field

from app.domains.common.base import APIModel
from app.domains.common.types import CandidateSessionStatus
from app.domains.tasks.schemas_public import TaskPublic


class CandidateInviteRequest(APIModel):
    """Schema for inviting a candidate to a simulation."""

    candidateName: str = Field(..., min_length=1, max_length=255)
    inviteEmail: EmailStr


class CandidateInviteResponse(APIModel):
    """Schema for the response after inviting a candidate."""

    candidateSessionId: int
    token: str
    inviteUrl: str


class CandidateSimulationSummary(APIModel):
    """Summary of the simulation for candidate session response."""

    id: int
    title: str
    role: str


class CandidateSessionResolveResponse(APIModel):
    """Schema for resolving a candidate session."""

    candidateSessionId: int
    status: CandidateSessionStatus
    startedAt: datetime | None
    completedAt: datetime | None
    candidateName: str
    simulation: CandidateSimulationSummary


class CandidateSessionVerifyRequest(APIModel):
    """Schema for verifying invite email for a candidate session."""

    email: EmailStr


class CandidateSessionVerifyResponse(CandidateSessionResolveResponse):
    """Backward-compatible alias for candidate session claim responses."""

    pass


class ProgressSummary(APIModel):
    """Summary of progress for the candidate session."""

    completed: int
    total: int


class CandidateInviteListItem(APIModel):
    """Dashboard-friendly invite summary for candidates."""

    candidateSessionId: int
    simulationId: int
    simulationTitle: str
    role: str
    companyName: str | None
    status: CandidateSessionStatus
    progress: ProgressSummary
    lastActivityAt: datetime | None
    inviteCreatedAt: datetime | None
    expiresAt: datetime | None
    inviteToken: str | None = None
    isExpired: bool


class CurrentTaskResponse(APIModel):
    """Schema for the current task assigned to the candidate."""

    candidateSessionId: int
    status: CandidateSessionStatus
    currentDayIndex: int | None
    currentTask: TaskPublic | None
    completedTaskIds: list[int]
    progress: ProgressSummary
    isComplete: bool


class CandidateSessionListItem(APIModel):
    """Schema for listing candidate sessions."""

    candidateSessionId: int
    inviteEmail: EmailStr
    candidateName: str
    status: CandidateSessionStatus
    startedAt: datetime | None
    completedAt: datetime | None
    hasReport: bool
