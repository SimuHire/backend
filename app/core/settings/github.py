from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class GithubSettings(BaseSettings):
    """GitHub integration configuration."""

    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_ORG: str = ""
    GITHUB_TOKEN: str = ""
    GITHUB_TEMPLATE_OWNER: str = ""
    GITHUB_ACTIONS_WORKFLOW_FILE: str = "tenon-ci.yml"
    GITHUB_REPO_PREFIX: str = "tenon-ws-"
    GITHUB_CLEANUP_ENABLED: bool = False

    model_config = SettingsConfigDict(extra="ignore", env_prefix="TENON_")
