from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TaskType = Literal["design", "code", "debug", "documentation"]


class SimulationCreate(BaseModel):
    """Payload for creating a simulation."""

    title: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    techStack: str = Field(..., min_length=1, max_length=500)
    seniority: str = Field(..., min_length=1, max_length=100)
    focus: str = Field(..., min_length=1, max_length=1000)


class TaskOut(BaseModel):
    """Response model for a created task."""

    id: int
    day_index: int
    type: TaskType
    title: str = Field(..., min_length=1, max_length=200)

    class Config:
        """Pydantic configuration."""

        from_attributes = True


class SimulationCreateResponse(BaseModel):
    """Response returned after creating a simulation."""

    id: int
    title: str
    role: str
    techStack: str
    seniority: str
    focus: str
    tasks: list[TaskOut]

    class Config:
        """Pydantic configuration."""

        from_attributes = True
