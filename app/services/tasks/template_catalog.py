from __future__ import annotations

from app.services.tasks.template_catalog_data import (
    ALLOWED_TEMPLATE_KEYS,
    DEFAULT_TEMPLATE_KEY,
    LEGACY_TEMPLATE_REPO_REWRITES,
    TEMPLATE_CATALOG,
)


class TemplateKeyError(ValueError):
    """Raised when a template key is invalid."""


def validate_template_key(template_key: str) -> str:
    if not isinstance(template_key, str):
        raise TemplateKeyError("templateKey must be a string")
    normalized = template_key.strip()
    if normalized not in ALLOWED_TEMPLATE_KEYS:
        allowed = ", ".join(sorted(ALLOWED_TEMPLATE_KEYS))
        raise TemplateKeyError(f"Invalid templateKey. Allowed values: {allowed}")
    return normalized


def resolve_template_repo_full_name(template_key: str) -> str:
    return TEMPLATE_CATALOG[validate_template_key(template_key)]["repo_full_name"]


def normalize_template_repo_value(
    template_repo: str | None, *, template_key: str | None = None
) -> str | None:
    template_repo = (template_repo or "").strip()
    validated_key: str | None = None
    if template_key:
        try:
            validated_key = validate_template_key(template_key)
        except TemplateKeyError:
            validated_key = None
    default_repo = resolve_template_repo_full_name(DEFAULT_TEMPLATE_KEY)
    if template_repo in LEGACY_TEMPLATE_REPO_REWRITES:
        return (
            resolve_template_repo_full_name(validated_key)
            if validated_key
            else default_repo
        )
    if template_repo:
        return template_repo
    if validated_key:
        return resolve_template_repo_full_name(validated_key)
    return None
