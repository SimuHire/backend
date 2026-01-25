from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .parsers import parse_env_list


class CorsSettings(BaseSettings):
    """CORS configuration."""

    CORS_ALLOW_ORIGINS: list[str] | str = Field(default_factory=list)
    CORS_ALLOW_ORIGIN_REGEX: str | None = None

    model_config = SettingsConfigDict(extra="ignore", env_prefix="TENON_")

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def _coerce_origins(cls, value):
        return parse_env_list(value)
