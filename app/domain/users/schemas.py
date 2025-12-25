from pydantic import ConfigDict

from app.domain.common.base import APIModel


class UserRead(APIModel):
    """Serialized user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
