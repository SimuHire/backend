from __future__ import annotations

# NOTE: This package keeps env parsing centralized while feature-scoped configs land.
from .auth import AuthSettings
from .claims import claim_namespace, claim_uri
from .cors import CorsSettings
from .database import DatabaseSettings
from .defaults import DEFAULT_CLAIM_NAMESPACE, normalize_sync_url, to_async_url
from .email import EmailSettings
from .github import GithubSettings
from .parsers import parse_env_list
from .settings import Settings

_normalize_sync_url = normalize_sync_url
_to_async_url = to_async_url

settings = Settings()

__all__ = [
    "AuthSettings",
    "CorsSettings",
    "DatabaseSettings",
    "DEFAULT_CLAIM_NAMESPACE",
    "EmailSettings",
    "GithubSettings",
    "Settings",
    "claim_namespace",
    "claim_uri",
    "parse_env_list",
    "settings",
    "normalize_sync_url",
    "to_async_url",
    "_normalize_sync_url",
    "_to_async_url",
]
