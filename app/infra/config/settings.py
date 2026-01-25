from __future__ import annotations

# This module intentionally exceeds 50 LOC: keeping one Pydantic BaseSettings
# class preserves env parsing/back-compat shims without scattering validators.
import os

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .auth import AuthSettings
from .cors import CorsSettings
from .database import DatabaseSettings
from .email import EmailSettings
from .github import GithubSettings
from .merge import merge_nested_settings
from .parsers import parse_env_list


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        env_nested_delimiter="__",
        env_prefix="TENON_",
    )

    ENV: str = "local"
    API_PREFIX: str = "/api"
    RATE_LIMIT_ENABLED: bool | None = None
    MAX_REQUEST_BODY_BYTES: int = 1_048_576
    DEBUG_PERF: bool = False
    TRUSTED_PROXY_CIDRS: list[str] | str = Field(default_factory=list)
    DEV_AUTH_BYPASS: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEV_AUTH_BYPASS", "TENON_DEV_AUTH_BYPASS"),
    )

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

    GITHUB_API_BASE: str | None = None
    GITHUB_ORG: str | None = None
    GITHUB_TOKEN: str | None = None
    GITHUB_TEMPLATE_OWNER: str | None = None
    GITHUB_ACTIONS_WORKFLOW_FILE: str | None = None
    GITHUB_REPO_PREFIX: str | None = None
    GITHUB_CLEANUP_ENABLED: bool | None = None

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    github: GithubSettings = Field(default_factory=GithubSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)

    CANDIDATE_PORTAL_BASE_URL: str = ""
    ADMIN_API_KEY: str = ""

    @field_validator("TRUSTED_PROXY_CIDRS", mode="before")
    @classmethod
    def _coerce_trusted_proxy_cidrs(cls, value):
        return parse_env_list(value)

    @model_validator(mode="before")
    def _merge_legacy(cls, values: dict) -> dict:
        return merge_nested_settings(values)

    @model_validator(mode="after")
    def _fail_fast_auth(self):
        env = str(self.ENV or "").lower()
        if env != "test":
            issuer_val = (self.auth.AUTH0_ISSUER or "").strip()
            domain_val = (self.auth.AUTH0_DOMAIN or "").strip()
            if not issuer_val and not domain_val:
                raise ValueError(
                    "AUTH0_ISSUER (or AUTH0_DOMAIN) must be set for Auth0 validation"
                )
            if not (self.auth.AUTH0_API_AUDIENCE or "").strip():
                raise ValueError("AUTH0_API_AUDIENCE must be set for Auth0 validation")
        return self

    @property
    def database_url_sync(self) -> str:  # pragma: no cover - shim
        return self.database.sync_url

    @property
    def database_url_async(self) -> str:  # pragma: no cover - shim
        return self.database.async_url

    @property
    def auth0_issuer(self) -> str:  # pragma: no cover - shim
        return self.auth.issuer

    @property
    def auth0_jwks_url(self) -> str:  # pragma: no cover - shim
        return self.auth.jwks_url

    @property
    def auth0_audience(self) -> str:  # pragma: no cover - shim
        return self.auth.audience

    @property
    def auth0_algorithms(self) -> list[str]:  # pragma: no cover - shim
        return self.auth.algorithms

    def __getattr__(self, name: str):
        if name == "AUTH0_JWKS_URL":
            return self.auth.AUTH0_JWKS_URL
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value):
        if name == "AUTH0_JWKS_URL":
            self.auth.AUTH0_JWKS_URL = value
            return
        super().__setattr__(name, value)

    @property
    def dev_auth_bypass_enabled(self) -> bool:
        env_val = os.getenv("DEV_AUTH_BYPASS")
        if env_val is None:
            env_val = os.getenv("TENON_DEV_AUTH_BYPASS")
        value = (env_val if env_val is not None else self.DEV_AUTH_BYPASS) or ""
        return value.strip() == "1"
