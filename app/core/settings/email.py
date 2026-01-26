from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    """Email provider configuration."""

    TENON_EMAIL_PROVIDER: str = "console"
    TENON_EMAIL_FROM: str = "Tenon <notifications@tenon.com>"
    TENON_RESEND_API_KEY: str = ""
    SENDGRID_API_KEY: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")
