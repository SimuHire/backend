from pydantic import BaseModel


class TaskPublic(BaseModel):
    """Public-facing task schema for candidates. Keeps only what the candidate needs to see."""

    id: int
    dayIndex: int
    title: str
    type: str
    description: str
