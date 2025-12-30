from app.domains.common.base import APIModel


class TaskPublic(APIModel):
    """Public-facing task schema for candidates. Keeps only what the candidate needs to see."""

    id: int
    dayIndex: int
    title: str
    type: str
    description: str
