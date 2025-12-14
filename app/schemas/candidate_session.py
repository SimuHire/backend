from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.task import TaskPublic


class CandidateInviteRequest(BaseModel):
    """Schema for inviting a candidate to a simulation."""

    candidateName: str = Field(..., min_length=1, max_length=255)
    inviteEmail: EmailStr


class CandidateInviteResponse(BaseModel):
    """Schema for the response after inviting a candidate."""

    candidateSessionId: int
    token: str
    inviteUrl: str


class CandidateSimulationSummary(BaseModel):
    """Summary of the simulation for candidate session response."""

    id: int
    title: str
    role: str


class CandidateSessionResolveResponse(BaseModel):
    """Schema for resolving a candidate session."""

    candidateSessionId: int
    status: str
    startedAt: datetime | None
    completedAt: datetime | None
    candidateName: str
    simulation: CandidateSimulationSummary


class ProgressSummary(BaseModel):
    """Summary of progress for the candidate session."""

    completed: int
    total: int


class CurrentTaskResponse(BaseModel):
    """Schema for the current task assigned to the candidate."""

    candidateSessionId: int
    status: str
    currentDayIndex: int | None
    currentTask: TaskPublic | None
    completedTaskIds: list[int]
    progress: ProgressSummary
    isComplete: bool
