from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.common.types import TaskType
from app.domain.simulations.task_schema import TaskPublic

__all__ = [
    "SimulationCreate",
    "TaskOut",
    "SimulationCreateResponse",
    "SimulationListItem",
    "TaskPublic",
]


class SimulationCreate(BaseModel):
    """Payload for creating a simulation."""

    title: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    techStack: str = Field(..., min_length=1, max_length=500)
    seniority: str = Field(..., min_length=1, max_length=100)
    focus: str = Field(..., min_length=1, max_length=1000)


class TaskOut(BaseModel):
    """Response model for a created task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    day_index: int
    type: TaskType
    title: str = Field(..., min_length=1, max_length=200)


class SimulationCreateResponse(BaseModel):
    """Response returned after creating a simulation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    role: str
    techStack: str
    seniority: str
    focus: str
    tasks: list[TaskOut]


class SimulationListItem(BaseModel):
    """List item for recruiter dashboard simulations."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    role: str
    techStack: str
    createdAt: datetime
    numCandidates: int
