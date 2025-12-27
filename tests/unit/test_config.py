import pytest

from app.core.config import Settings


def test_database_url_sync_normalizes_postgres_scheme():
    s = Settings(
        DATABASE_URL_SYNC="postgres://user:pass@localhost:5432/db",
        DATABASE_URL="",
    )
    assert s.database_url_sync == "postgresql://user:pass@localhost:5432/db"


def test_database_url_sync_raises_when_missing():
    s = Settings(DATABASE_URL="", DATABASE_URL_SYNC="")
    with pytest.raises(ValueError):
        _ = s.database_url_sync


def test_database_url_async_adds_asyncpg_driver():
    s = Settings(
        DATABASE_URL="postgresql://user:pass@localhost:5432/dbname",
        DATABASE_URL_SYNC="postgresql://user:pass@localhost:5432/dbname",
    )
    assert (
        s.database_url_async == "postgresql+asyncpg://user:pass@localhost:5432/dbname"
    )


def test_auth0_helpers_default_to_domain():
    s = Settings(
        AUTH0_DOMAIN="example.auth0.com",
        AUTH0_ALGORITHMS="RS256, HS256",
        AUTH0_API_AUDIENCE="api://test",
        AUTH0_ISSUER="",
        AUTH0_JWKS_URL="",
    )

    assert s.auth0_issuer == "https://example.auth0.com/"
    assert s.auth0_jwks_url == "https://example.auth0.com/.well-known/jwks.json"
    assert s.auth0_algorithms == ["RS256", "HS256"]


def test_github_settings_merge_flat_env():
    s = Settings(
        GITHUB_API_BASE="https://api.github.com",
        GITHUB_ORG="simuhire",
        GITHUB_TOKEN="ghp_123",
        GITHUB_TEMPLATE_OWNER="simuhire-templates",
        GITHUB_ACTIONS_WORKFLOW_FILE="ci.yml",
        GITHUB_REPO_PREFIX="prefix-",
        GITHUB_CLEANUP_ENABLED="True",
    )

    assert s.github.GITHUB_API_BASE == "https://api.github.com"
    assert s.github.GITHUB_ORG == "simuhire"
    assert s.github.GITHUB_TOKEN == "ghp_123"
    assert s.github.GITHUB_TEMPLATE_OWNER == "simuhire-templates"
    assert s.github.GITHUB_ACTIONS_WORKFLOW_FILE == "ci.yml"
    assert s.github.GITHUB_REPO_PREFIX == "prefix-"
    assert s.github.GITHUB_CLEANUP_ENABLED is True
