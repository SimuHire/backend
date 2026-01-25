from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .claims import claim_namespace, claim_uri
from .defaults import DEFAULT_CLAIM_NAMESPACE


class AuthSettings(BaseSettings):
    AUTH0_DOMAIN: str = ""
    AUTH0_ISSUER: str | None = None
    AUTH0_JWKS_URL: str | None = None
    AUTH0_API_AUDIENCE: str = ""
    AUTH0_ALGORITHMS: str = "RS256"
    AUTH0_LEEWAY_SECONDS: int = 60
    AUTH0_JWKS_CACHE_TTL_SECONDS: int = 3600
    AUTH0_CLAIM_NAMESPACE: str = DEFAULT_CLAIM_NAMESPACE
    AUTH0_EMAIL_CLAIM: str = ""
    AUTH0_ROLES_CLAIM: str = ""
    AUTH0_PERMISSIONS_CLAIM: str = ""
    model_config = SettingsConfigDict(extra="ignore", env_prefix="TENON_")

    @property
    def issuer(self) -> str:
        issuer = (self.AUTH0_ISSUER or f"https://{self.AUTH0_DOMAIN}/").strip()
        return issuer if issuer.endswith("/") else f"{issuer}/"

    @property
    def jwks_url(self) -> str:
        return (
            self.AUTH0_JWKS_URL or f"https://{self.AUTH0_DOMAIN}/.well-known/jwks.json"
        )

    @property
    def audience(self) -> str:  # alias for backward compatibility
        return self.AUTH0_API_AUDIENCE

    @property
    def algorithms(self) -> list[str]:
        return [p.strip() for p in self.AUTH0_ALGORITHMS.split(",") if p.strip()] or [
            "RS256"
        ]

    @model_validator(mode="after")
    def _apply_claim_namespace(self):
        ns = claim_namespace(self.AUTH0_CLAIM_NAMESPACE)
        self.AUTH0_EMAIL_CLAIM = self.AUTH0_EMAIL_CLAIM or claim_uri(ns, "email")
        self.AUTH0_ROLES_CLAIM = self.AUTH0_ROLES_CLAIM or claim_uri(ns, "roles")
        self.AUTH0_PERMISSIONS_CLAIM = self.AUTH0_PERMISSIONS_CLAIM or claim_uri(
            ns, "permissions"
        )
        return self

    permissions_str_claim = property(
        lambda self: claim_uri(self.AUTH0_CLAIM_NAMESPACE, "permissions_str")
    )
    name_claim = property(lambda self: claim_uri(self.AUTH0_CLAIM_NAMESPACE, "name"))
