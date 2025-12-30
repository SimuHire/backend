from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base schema with sensible defaults for API responses."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
