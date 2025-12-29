import pytest

from app.core.config import CorsSettings, Settings, _to_async_url


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


def test_settings_attr_passthroughs_and_errors():
    s = Settings(
        AUTH0_DOMAIN="example.auth0.com",
        AUTH0_JWKS_URL="https://example.auth0.com/.well-known/jwks.json",
    )
    # __setattr__/__getattr__ passthrough
    s.AUTH0_JWKS_URL = "https://override.test/jwks.json"

    with pytest.raises(AttributeError):
        _ = s.MISSING_FIELD

    assert s.auth.AUTH0_JWKS_URL == "https://override.test/jwks.json"


def test_settings_merge_env(monkeypatch):
    monkeypatch.setenv("AUTH0_DOMAIN", "env-domain.auth0.com")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://a.com"]')
    monkeypatch.setenv("GITHUB_API_BASE", "https://api.github.com")
    s = Settings()
    assert s.auth.AUTH0_DOMAIN == "env-domain.auth0.com"
    assert ["https://a.com"] == s.cors.CORS_ALLOW_ORIGINS
    assert s.github.GITHUB_API_BASE == "https://api.github.com"


def test_settings_merge_env_prefers_env_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://env-db")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", "https://.*\\.example.com")
    s = Settings(database={}, cors={})
    assert s.database.DATABASE_URL == "postgresql://env-db"
    assert s.cors.CORS_ALLOW_ORIGIN_REGEX == "https://.*\\.example.com"


def test_normalize_sync_url_noop_and_getattr_passthrough():
    s = Settings(DATABASE_URL_SYNC="postgresql://already-normalized")
    assert s.database.sync_url == "postgresql://already-normalized"
    # Force __getattr__ path for AUTH0_JWKS_URL
    assert Settings.__getattr__(s, "AUTH0_JWKS_URL") == s.auth.AUTH0_JWKS_URL


def test_cors_coercion_variants():
    settings = Settings(
        CORS_ALLOW_ORIGINS='["https://one.com", "https://two.com"]',
        CORS_ALLOW_ORIGIN_REGEX=None,
    )
    assert [
        "https://one.com",
        "https://two.com",
    ] == settings.cors.CORS_ALLOW_ORIGINS
    # Invalid JSON string falls back to comma split
    assert CorsSettings._coerce_origins("[bad") == ["[bad"]
    assert CorsSettings._coerce_origins("a.com, b.com") == ["a.com", "b.com"]


def test_merge_env_applies_nested_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://env-sync")
    monkeypatch.setenv("AUTH0_API_AUDIENCE", "api://aud")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", "^https://allowed")
    s = Settings(database={}, auth={}, cors={})
    assert s.database.DATABASE_URL_SYNC == "postgresql://env-sync"
    assert s.auth.AUTH0_API_AUDIENCE == "api://aud"
    assert s.cors.CORS_ALLOW_ORIGIN_REGEX == "^https://allowed"


def test_normalize_sync_url_passthrough():
    from app.core.config import _normalize_sync_url

    assert _normalize_sync_url("sqlite:///local.db") == "sqlite:///local.db"


def test_to_async_url_passthrough_and_coerce():
    assert _to_async_url("sqlite:///local.db") == "sqlite:///local.db"
    assert (
        _to_async_url("postgresql://user:pass@localhost/db")
        == "postgresql+asyncpg://user:pass@localhost/db"
    )


def test_merge_env_pulls_missing_sections(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.setenv("AUTH0_DOMAIN", "auth.example.com")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://a.com,https://b.com")
    monkeypatch.setenv("GITHUB_ORG", "org")
    s = Settings()
    assert s.database.DATABASE_URL == "postgresql://db"
    assert s.auth.AUTH0_DOMAIN == "auth.example.com"
    assert ["https://a.com", "https://b.com"] == s.cors.CORS_ALLOW_ORIGINS
    assert s.github.GITHUB_ORG == "org"


def test_merge_legacy_validator_uses_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://env-db")
    monkeypatch.setenv("AUTH0_ISSUER", "https://issuer.test")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", "^https://allowed")
    values = {}
    merged = Settings._merge_legacy(values)
    assert merged["database"]["DATABASE_URL_SYNC"] == "postgresql://env-db"
    assert merged["auth"]["AUTH0_ISSUER"] == "https://issuer.test"
    assert merged["cors"]["CORS_ALLOW_ORIGIN_REGEX"] == "^https://allowed"


def test_cors_coerce_fallback_returns_value():
    assert CorsSettings._coerce_origins(123) == 123
