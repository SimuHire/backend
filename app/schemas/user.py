from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    """Serialized user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
