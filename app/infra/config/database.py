from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .defaults import normalize_sync_url, to_async_url


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    DATABASE_URL: str = Field(default="")
    DATABASE_URL_SYNC: str = Field(default="")

    model_config = SettingsConfigDict(extra="ignore", env_prefix="TENON_")

    @property
    def sync_url(self) -> str:
        """Sync DSN for Alembic / sync SQLAlchemy."""
        url = self.DATABASE_URL_SYNC or self.DATABASE_URL
        if not url:
            raise ValueError("DATABASE_URL_SYNC or DATABASE_URL must be set")
        return normalize_sync_url(url)

    @property
    def async_url(self) -> str:
        """Async DSN for SQLAlchemy async engine (asyncpg)."""
        return to_async_url(self.sync_url)
