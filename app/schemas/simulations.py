from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from app.domains.common.types import TaskType
from app.domains.tasks.schemas_public import TaskPublic
from app.services.tasks.template_catalog import (
    DEFAULT_TEMPLATE_KEY,
    TemplateKeyError,
    validate_template_key,
)

__all__ = [
    "SimulationCreate",
    "TaskOut",
    "SimulationCreateResponse",
    "SimulationListItem",
    "SimulationDetailResponse",
    "SimulationDetailTask",
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


class SimulationDetailTask(BaseModel):
    """Task summary for recruiter simulation detail view."""

    model_config = ConfigDict(from_attributes=True)

    dayIndex: int
    title: str | None = None
    type: TaskType | None = None
    description: str | None = None
    rubric: str | list[str] | dict | None = None
    maxScore: int | None = None
    preProvisioned: bool | None = None
    templateRepoFullName: str | None = None

    @model_serializer(mode="plain")
    def _serialize(self):
        data = {
            "dayIndex": self.dayIndex,
            "title": self.title,
            "type": self.type,
            "description": self.description,
            "rubric": self.rubric,
        }
        if self.maxScore is not None:
            data["maxScore"] = self.maxScore
        if self.preProvisioned is not None:
            data["preProvisioned"] = self.preProvisioned
        if self.templateRepoFullName is not None:
            data["templateRepoFullName"] = self.templateRepoFullName
        return data


class SimulationDetailResponse(BaseModel):
    """Detail view response for a simulation (recruiter-only)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None = None
    templateKey: str | None = None
    role: str | None = None
    techStack: str | list[str] | None = None
    focus: str | list[str] | None = None
    scenario: str | None = None
    tasks: list[SimulationDetailTask]
