from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ENV: str = "local"
    API_PREFIX: str = "/api"

    DATABASE_URL: str = ""
    DATABASE_URL_SYNC: str = ""

    JWT_SECRET: str = "CHANGE_ME"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24

    AUTH0_DOMAIN: str = ""
    AUTH0_ISSUER: str | None = None
    AUTH0_JWKS_URL: str | None = None
    AUTH0_API_AUDIENCE: str = ""
    AUTH0_ALGORITHMS: str = "RS256"

    AUTH0_CLIENT_ID: str | None = None
    AUTH0_CLIENT_SECRET: str | None = None

    @property
    def database_url_sync(self) -> str:
        """Sync DSN for Alembic / sync SQLAlchemy.

        Render commonly provides:
          - postgres://...
          - postgresql://...
        We normalize postgres:// -> postgresql://.
        """
        url = self.DATABASE_URL_SYNC or self.DATABASE_URL
        if not url:
            raise ValueError("DATABASE_URL_SYNC or DATABASE_URL must be set")

        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]

        return url

    @property
    def database_url_async(self) -> str:
        """Async DSN for SQLAlchemy async engine (asyncpg).
        Converts postgresql://... -> postgresql+asyncpg://...
        """
        url = self.database_url_sync

        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        return url

    @property
    def auth0_issuer(self) -> str:
        if self.AUTH0_ISSUER:
            return self.AUTH0_ISSUER
        return f"https://{self.AUTH0_DOMAIN}/"

    @property
    def auth0_jwks_url(self) -> str:
        if self.AUTH0_JWKS_URL:
            return self.AUTH0_JWKS_URL
        return f"https://{self.AUTH0_DOMAIN}/.well-known/jwks.json"

    @property
    def auth0_audience(self) -> str:
        return self.AUTH0_API_AUDIENCE

    @property
    def auth0_algorithms(self) -> list[str]:
        parts = [part.strip() for part in self.AUTH0_ALGORITHMS.split(",") if part.strip()]
        return parts or ["RS256"]


settings = Settings()
