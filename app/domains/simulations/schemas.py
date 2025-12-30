from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.common.types import TaskType
from app.domains.tasks.schemas_public import TaskPublic
from app.domains.tasks.template_catalog import (
    DEFAULT_TEMPLATE_KEY,
    TemplateKeyError,
    validate_template_key,
)

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
    templateKey: str = Field(
        DEFAULT_TEMPLATE_KEY, min_length=1, max_length=255, description="Template key"
    )

    @field_validator("templateKey")
    @classmethod
    def _validate_template_key(cls, value: str) -> str:
        try:
            return validate_template_key(value)
        except TemplateKeyError as exc:
            raise ValueError(str(exc)) from None


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
    templateKey: str
    tasks: list[TaskOut]


class SimulationListItem(BaseModel):
    """List item for recruiter dashboard simulations."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    role: str
    techStack: str
    templateKey: str
    createdAt: datetime
    numCandidates: int
