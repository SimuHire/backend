from __future__ import annotations

import json
import os

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_sync_url(url: str) -> str:
    """Normalize postgres:// -> postgresql:// for sync DSNs."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _to_async_url(url: str) -> str:
    """Convert sync URL to asyncpg URL if needed."""
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    DATABASE_URL: str = Field(default="")
    DATABASE_URL_SYNC: str = Field(default="")

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def sync_url(self) -> str:
        """Sync DSN for Alembic / sync SQLAlchemy."""
        url = self.DATABASE_URL_SYNC or self.DATABASE_URL
        if not url:
            raise ValueError("DATABASE_URL_SYNC or DATABASE_URL must be set")
        return _normalize_sync_url(url)

    @property
    def async_url(self) -> str:
        """Async DSN for SQLAlchemy async engine (asyncpg)."""
        return _to_async_url(self.sync_url)


class AuthSettings(BaseSettings):
    """Auth-related configuration (Auth0 + JWT compatibility)."""

    AUTH0_DOMAIN: str = ""
    AUTH0_ISSUER: str | None = None
    AUTH0_JWKS_URL: str | None = None
    AUTH0_API_AUDIENCE: str = ""
    AUTH0_ALGORITHMS: str = "RS256"

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def issuer(self) -> str:
        """Issuer URL used to validate Auth0 tokens."""
        if self.AUTH0_ISSUER:
            return self.AUTH0_ISSUER
        return f"https://{self.AUTH0_DOMAIN}/"

    @property
    def jwks_url(self) -> str:
        """JWKS endpoint for Auth0 public keys."""
        if self.AUTH0_JWKS_URL:
            return self.AUTH0_JWKS_URL
        return f"https://{self.AUTH0_DOMAIN}/.well-known/jwks.json"

    @property
    def audience(self) -> str:
        """Expected API audience for Auth0 tokens."""
        return self.AUTH0_API_AUDIENCE

    @property
    def algorithms(self) -> list[str]:
        """Allowed JWT signing algorithms."""
        parts = [
            part.strip() for part in self.AUTH0_ALGORITHMS.split(",") if part.strip()
        ]
        return parts or ["RS256"]


class CorsSettings(BaseSettings):
    """CORS configuration."""

    CORS_ALLOW_ORIGINS: list[str] | str = Field(default_factory=list)
    CORS_ALLOW_ORIGIN_REGEX: str | None = None

    model_config = SettingsConfigDict(extra="ignore")

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def _coerce_origins(cls, value):
        """Allow empty string, JSON array, or comma-separated CORS env values."""
        if value in (None, "", [], (), "[]", "null", "None"):
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [p.strip() for p in text.split(",") if p.strip()]
        return value


class GithubSettings(BaseSettings):
    """GitHub integration configuration."""

    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_ORG: str = ""
    GITHUB_TOKEN: str = ""
    GITHUB_TEMPLATE_OWNER: str = ""
    GITHUB_ACTIONS_WORKFLOW_FILE: str = "simuhire-ci.yml"
    GITHUB_REPO_PREFIX: str = "simuhire-candidate-"
    GITHUB_CLEANUP_ENABLED: bool = False

    model_config = SettingsConfigDict(extra="ignore")


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        env_nested_delimiter="__",
    )

    ENV: str = "local"
    API_PREFIX: str = "/api"

    # Flat env hooks (loaded from .env and merged into nested models)
    DATABASE_URL: str | None = None
    DATABASE_URL_SYNC: str | None = None

    AUTH0_DOMAIN: str | None = None
    AUTH0_ISSUER: str | None = None
    AUTH0_JWKS_URL: str | None = None
    AUTH0_API_AUDIENCE: str | None = None
    AUTH0_ALGORITHMS: str | None = None

    CORS_ALLOW_ORIGINS: str | list[str] | None = None
    CORS_ALLOW_ORIGIN_REGEX: str | None = None

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    github: GithubSettings = Field(default_factory=GithubSettings)

    CANDIDATE_PORTAL_BASE_URL: str = ""

    @model_validator(mode="before")
    def _merge_legacy(cls, values: dict) -> dict:
        """Allow legacy flat fields to populate nested settings."""
        data = dict(values)

        db_keys = {"DATABASE_URL", "DATABASE_URL_SYNC"}
        auth_keys = {
            "AUTH0_DOMAIN",
            "AUTH0_ISSUER",
            "AUTH0_JWKS_URL",
            "AUTH0_API_AUDIENCE",
            "AUTH0_ALGORITHMS",
        }
        cors_keys = {"CORS_ALLOW_ORIGINS", "CORS_ALLOW_ORIGIN_REGEX"}
        github_keys = {
            "GITHUB_API_BASE",
            "GITHUB_ORG",
            "GITHUB_TOKEN",
            "GITHUB_TEMPLATE_OWNER",
            "GITHUB_ACTIONS_WORKFLOW_FILE",
            "GITHUB_REPO_PREFIX",
            "GITHUB_CLEANUP_ENABLED",
        }

        db_data = dict(data.get("database", {}) or {})
        for key in db_keys:
            if key in data:
                db_data[key] = data.pop(key)
            elif (env_val := os.getenv(key)) is not None:
                db_data[key] = env_val
        if db_data:
            data["database"] = db_data

        auth_data = dict(data.get("auth", {}) or {})
        for key in auth_keys:
            if key in data:
                auth_data[key] = data.pop(key)
            elif (env_val := os.getenv(key)) is not None:
                auth_data[key] = env_val
        if auth_data:
            data["auth"] = auth_data

        cors_data = dict(data.get("cors", {}) or {})
        for key in cors_keys:
            if key in data:
                cors_data[key] = data.pop(key)
            elif (env_val := os.getenv(key)) is not None:
                cors_data[key] = env_val
        if cors_data:
            data["cors"] = cors_data

        github_data = dict(data.get("github", {}) or {})
        for key in github_keys:
            if key in data:
                github_data[key] = data.pop(key)
            elif (env_val := os.getenv(key)) is not None:
                github_data[key] = env_val
        if github_data:
            data["github"] = github_data

        return data

    # Backwards compatibility shims for existing imports
    @property
    def database_url_sync(self) -> str:  # pragma: no cover - shim
        """Backward-compatible alias for sync DB URL."""
        return self.database.sync_url

    @property
    def database_url_async(self) -> str:  # pragma: no cover - shim
        """Backward-compatible alias for async DB URL."""
        return self.database.async_url

    @property
    def auth0_issuer(self) -> str:  # pragma: no cover - shim
        """Backward-compatible Auth0 issuer getter."""
        return self.auth.issuer

    @property
    def auth0_jwks_url(self) -> str:  # pragma: no cover - shim
        """Backward-compatible Auth0 JWKS URL getter."""
        return self.auth.jwks_url

    @property
    def auth0_audience(self) -> str:  # pragma: no cover - shim
        """Backward-compatible Auth0 audience getter."""
        return self.auth.audience

    @property
    def auth0_algorithms(self) -> list[str]:  # pragma: no cover - shim
        """Backward-compatible Auth0 algorithms getter."""
        return self.auth.algorithms

    def __getattr__(self, name: str):
        """Backwards-compatible passthrough for legacy flat settings."""
        if name == "AUTH0_JWKS_URL":
            return self.auth.AUTH0_JWKS_URL
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value):
        """Allow tests/dev code to set AUTH0_JWKS_URL directly on settings."""
        if name == "AUTH0_JWKS_URL":
            self.auth.AUTH0_JWKS_URL = value
            return
        super().__setattr__(name, value)


settings = Settings()
