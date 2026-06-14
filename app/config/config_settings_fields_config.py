"""Application module for config settings fields config workflows."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_auth_config import AuthSettings
from .config_cors_config import CorsSettings
from .config_database_config import DatabaseSettings
from .config_email_config import EmailSettings
from .config_github_config import GithubSettings
from .config_storage_media_config import StorageMediaSettings


class SettingsFields(BaseSettings):
    """Represent settings fields data and behavior."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="allow",
        env_nested_delimiter="__",
        env_prefix="WINOE_",
    )

    ENV: str = "local"
    API_PREFIX: str = "/api"
    RATE_LIMIT_ENABLED: bool | None = None
    MAX_REQUEST_BODY_BYTES: int = 1_048_576
    DEBUG_PERF: bool = False
    PERF_SPANS_ENABLED: bool = False
    PERF_SQL_FINGERPRINTS_ENABLED: bool = False
    PERF_SPAN_SAMPLE_RATE: float = 1.0
    TRUSTED_PROXY_CIDRS: list[str] | str = Field(default_factory=list)
    DEMO_MODE: bool = False
    DEMO_ADMIN_ALLOWLIST_EMAILS: list[str] | str = Field(default_factory=list)
    DEMO_ADMIN_ALLOWLIST_SUBJECTS: list[str] | str = Field(default_factory=list)
    DEMO_ADMIN_ALLOWLIST_TALENT_PARTNER_IDS: list[int] | str = Field(
        default_factory=list
    )
    DEMO_ADMIN_JOB_STALE_SECONDS: int = 900
    JOB_HEALTH_MAX_STUCK_JOBS: int = 0
    JOB_HEALTH_MAX_OLDEST_QUEUED_SECONDS: int = 1800
    JOB_HEALTH_MAX_DLQ_COUNT: int = 0
    WORKER_HEARTBEAT_INTERVAL_SECONDS: int = 15
    WORKER_HEARTBEAT_STALE_SECONDS: int = 60
    AI_RUNTIME_MODE: str = "real"
    DEV_AUTH_BYPASS: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEV_AUTH_BYPASS", "WINOE_DEV_AUTH_BYPASS"),
    )
    SCHEDULE_DAY_WINDOW_OVERRIDES_ENABLED: bool = False
    OPENAI_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "WINOE_OPENAI_API_KEY"),
    )
    ANTHROPIC_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "WINOE_ANTHROPIC_API_KEY"),
    )

    SCENARIO_GENERATION_RUNTIME_MODE: str | None = None
    SCENARIO_GENERATION_PROVIDER: str = "anthropic"
    SCENARIO_GENERATION_MODEL: str = "claude-opus-4-7"
    SCENARIO_GENERATION_TIMEOUT_SECONDS: int = 120
    SCENARIO_GENERATION_MAX_RETRIES: int = 2
    SCENARIO_GENERATION_FALLBACK_PROVIDER: str = "openai"
    SCENARIO_GENERATION_FALLBACK_MODEL: str = "gpt-5.5"

    WINOE_REPORT_DAY1_RUNTIME_MODE: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WINOE_REPORT_DAY1_RUNTIME_MODE",
            "WINOE_WINOE_REPORT_DAY1_RUNTIME_MODE",
        ),
    )
    WINOE_REPORT_DAY1_PROVIDER: str = "anthropic"
    WINOE_REPORT_DAY1_MODEL: str = "claude-opus-4-7"
    WINOE_REPORT_DAY1_TIMEOUT_SECONDS: int = 90
    WINOE_REPORT_DAY1_MAX_RETRIES: int = 2
    WINOE_REPORT_DAY1_FALLBACK_PROVIDER: str = "openai"
    WINOE_REPORT_DAY1_FALLBACK_MODEL: str = "gpt-5.5"

    WINOE_REPORT_DAY23_RUNTIME_MODE: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WINOE_REPORT_DAY23_RUNTIME_MODE",
            "WINOE_WINOE_REPORT_DAY23_RUNTIME_MODE",
        ),
    )
    WINOE_REPORT_DAY23_PROVIDER: str = "openai"
    WINOE_REPORT_DAY23_MODEL: str = "gpt-5.5"
    WINOE_REPORT_DAY23_TIMEOUT_SECONDS: int = 120
    WINOE_REPORT_DAY23_MAX_RETRIES: int = 2
    WINOE_REPORT_DAY23_FALLBACK_PROVIDER: str = "anthropic"
    WINOE_REPORT_DAY23_FALLBACK_MODEL: str = "claude-sonnet-4-6"

    WINOE_REPORT_DAY4_RUNTIME_MODE: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WINOE_REPORT_DAY4_RUNTIME_MODE",
            "WINOE_WINOE_REPORT_DAY4_RUNTIME_MODE",
        ),
    )
    WINOE_REPORT_DAY4_PROVIDER: str = "anthropic"
    WINOE_REPORT_DAY4_MODEL: str = "claude-sonnet-4-6"
    WINOE_REPORT_DAY4_TIMEOUT_SECONDS: int = 90
    WINOE_REPORT_DAY4_MAX_RETRIES: int = 2
    WINOE_REPORT_DAY4_FALLBACK_PROVIDER: str = "openai"
    WINOE_REPORT_DAY4_FALLBACK_MODEL: str = "gpt-5.5"

    WINOE_REPORT_DAY5_RUNTIME_MODE: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WINOE_REPORT_DAY5_RUNTIME_MODE",
            "WINOE_WINOE_REPORT_DAY5_RUNTIME_MODE",
        ),
    )
    WINOE_REPORT_DAY5_PROVIDER: str = "anthropic"
    WINOE_REPORT_DAY5_MODEL: str = "claude-sonnet-4-6"
    WINOE_REPORT_DAY5_TIMEOUT_SECONDS: int = 90
    WINOE_REPORT_DAY5_MAX_RETRIES: int = 2
    WINOE_REPORT_DAY5_FALLBACK_PROVIDER: str = "openai"
    WINOE_REPORT_DAY5_FALLBACK_MODEL: str = "gpt-5.5"

    WINOE_REPORT_AGGREGATOR_RUNTIME_MODE: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WINOE_REPORT_AGGREGATOR_RUNTIME_MODE",
            "WINOE_WINOE_REPORT_AGGREGATOR_RUNTIME_MODE",
        ),
    )
    WINOE_REPORT_AGGREGATOR_PROVIDER: str = "openai"
    WINOE_REPORT_AGGREGATOR_MODEL: str = "gpt-5.5"
    WINOE_REPORT_AGGREGATOR_TIMEOUT_SECONDS: int = 90
    WINOE_REPORT_AGGREGATOR_MAX_RETRIES: int = 2
    WINOE_REPORT_AGGREGATOR_FALLBACK_PROVIDER: str = "anthropic"
    WINOE_REPORT_AGGREGATOR_FALLBACK_MODEL: str = "claude-sonnet-4-6"

    TRANSCRIPTION_RUNTIME_MODE: str | None = None
    TRANSCRIPTION_PROVIDER: str = "openai"
    TRANSCRIPTION_MODEL: str = "gpt-4o-transcribe"
    TRANSCRIPTION_TIMEOUT_SECONDS: int = 180
    TRANSCRIPTION_MAX_RETRIES: int = 2

    DATABASE_URL: str | None = None
    DATABASE_URL_SYNC: str | None = None
    AUTH0_DOMAIN: str | None = None
    AUTH0_ISSUER: str | None = None
    AUTH0_JWKS_URL: str | None = None
    AUTH0_API_AUDIENCE: str | None = None
    AUTH0_ALGORITHMS: str | None = None
    AUTH0_CLIENT_ID: str | None = None
    AUTH0_CLIENT_SECRET: str | None = None
    AUTH0_SESSION_SECRET: str | None = None
    CORS_ALLOW_ORIGINS: str | list[str] | None = None
    CORS_ALLOW_ORIGIN_REGEX: str | None = None
    CSRF_ALLOWED_ORIGINS: list[str] | str = Field(default_factory=list)
    CSRF_PROTECTED_PATH_PREFIXES: list[str] | str = Field(default_factory=list)

    GITHUB_API_BASE: str | None = None
    GITHUB_ORG: str | None = None
    GITHUB_TOKEN: str | None = None
    GITHUB_TEMPLATE_OWNER: str | None = None
    GITHUB_ACTIONS_WORKFLOW_FILE: str | None = None
    GITHUB_REPO_PREFIX: str | None = None
    GITHUB_CLEANUP_ENABLED: bool | None = None
    WORKSPACE_RETENTION_DAYS: int | None = None
    WORKSPACE_CLEANUP_MODE: str | None = None
    WORKSPACE_DELETE_ENABLED: bool | None = None
    GITHUB_WEBHOOK_SECRET: str | None = None
    GITHUB_WEBHOOK_MAX_BODY_BYTES: int | None = None

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    github: GithubSettings = Field(default_factory=GithubSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    storage_media: StorageMediaSettings = Field(default_factory=StorageMediaSettings)

    CANDIDATE_PORTAL_BASE_URL: str = ""
    ADMIN_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WINOE_ADMIN_API_KEY",
            "ADMIN_API_TOKEN",
            "ADMIN_API_KEY",
        ),
    )
