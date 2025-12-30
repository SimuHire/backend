"""Template catalog and validation helpers for simulation task templates."""

from __future__ import annotations

from typing import Any

DEFAULT_TEMPLATE_KEY = "python-fastapi"

TEMPLATE_CATALOG: dict[str, dict[str, Any]] = {
    # Backend-only templates
    "python-fastapi": {
        "repo_full_name": "simuhire-dev/simuhire-template-python-fastapi",
        "display_name": "Python (FastAPI)",
    },
    "node-express-ts": {
        "repo_full_name": "simuhire-dev/simuhire-template-node-express-ts",
        "display_name": "Node.js (Express, TS)",
    },
    "node-nest-ts": {
        "repo_full_name": "simuhire-dev/simuhire-template-node-nest-ts",
        "display_name": "Node.js (NestJS, TS)",
    },
    "java-springboot": {
        "repo_full_name": "simuhire-dev/simuhire-template-java-springboot",
        "display_name": "Java (Spring Boot)",
    },
    "go-gin": {
        "repo_full_name": "simuhire-dev/simuhire-template-go-gin",
        "display_name": "Go (Gin)",
    },
    "dotnet-webapi": {
        "repo_full_name": "simuhire-dev/simuhire-template-dotnet-webapi",
        "display_name": ".NET (Web API)",
    },
    # Web full-stack monorepos
    "monorepo-nextjs-nest": {
        "repo_full_name": "simuhire-dev/simuhire-template-monorepo-nextjs-nest",
        "display_name": "Monorepo (Next.js + NestJS)",
    },
    "monorepo-nextjs-fastapi": {
        "repo_full_name": "simuhire-dev/simuhire-template-monorepo-nextjs-fastapi",
        "display_name": "Monorepo (Next.js + FastAPI)",
    },
    "monorepo-react-express": {
        "repo_full_name": "simuhire-dev/simuhire-template-monorepo-react-express",
        "display_name": "Monorepo (React + Express)",
    },
    "monorepo-react-springboot": {
        "repo_full_name": "simuhire-dev/simuhire-template-monorepo-react-springboot",
        "display_name": "Monorepo (React + Spring Boot)",
    },
    # Mobile
    "mobile-fullstack-expo-fastapi": {
        "repo_full_name": "simuhire-dev/simuhire-template-monorepo-expo-fastapi",
        "display_name": "Mobile Fullstack (Expo + FastAPI)",
    },
    "mobile-backend-fastapi": {
        "repo_full_name": "simuhire-dev/simuhire-template-mobile-backend-fastapi",
        "display_name": "Mobile Backend (FastAPI)",
    },
    # ML
    "ml-backend-fastapi": {
        "repo_full_name": "simuhire-dev/simuhire-template-ml-backend-fastapi",
        "display_name": "ML Backend (FastAPI)",
    },
    "ml-infra-mlops": {
        "repo_full_name": "simuhire-dev/simuhire-template-ml-infra-mlops",
        "display_name": "ML Infra / MLOps",
    },
}

ALLOWED_TEMPLATE_KEYS: set[str] = set(TEMPLATE_CATALOG.keys())

# Legacy/bad template_repo values to be rewritten by migrations.
LEGACY_TEMPLATE_REPO_REWRITES: dict[str, str] = {
    "simuhire-templates/node-day2-api": TEMPLATE_CATALOG[DEFAULT_TEMPLATE_KEY][
        "repo_full_name"
    ],
    "simuhire-templates/node-day3-debug": TEMPLATE_CATALOG[DEFAULT_TEMPLATE_KEY][
        "repo_full_name"
    ],
    "simuhire-dev/simuhire-template-python": TEMPLATE_CATALOG["python-fastapi"][
        "repo_full_name"
    ],
}


class TemplateKeyError(ValueError):
    """Raised when a template key is invalid."""


def validate_template_key(template_key: str) -> str:
    """Normalize and validate a template key."""
    if not isinstance(template_key, str):
        raise TemplateKeyError("templateKey must be a string")
    normalized = template_key.strip()
    if normalized not in ALLOWED_TEMPLATE_KEYS:
        allowed = ", ".join(sorted(ALLOWED_TEMPLATE_KEYS))
        raise TemplateKeyError(f"Invalid templateKey. Allowed values: {allowed}")
    return normalized


def resolve_template_repo_full_name(template_key: str) -> str:
    """Return the template repository full name for the given key."""
    key = validate_template_key(template_key)
    return TEMPLATE_CATALOG[key]["repo_full_name"]


def normalize_template_repo_value(
    template_repo: str | None, *, template_key: str | None = None
) -> str | None:
    """Rewrite legacy/bad template_repo values when possible.

    This helper is reused in migrations and tests to ensure old values converge
    to the current catalog. It only rewrites known-bad values or fills blanks
    when a valid template_key is provided.
    """
    template_repo = (template_repo or "").strip()
    validated_key: str | None = None
    if template_key:
        try:
            validated_key = validate_template_key(template_key)
        except TemplateKeyError:
            validated_key = None

    default_repo = resolve_template_repo_full_name(DEFAULT_TEMPLATE_KEY)

    # Always rewrite the old python template to the FastAPI template.
    if template_repo == "simuhire-dev/simuhire-template-python":
        return default_repo

    if template_repo in LEGACY_TEMPLATE_REPO_REWRITES:
        if validated_key:
            return resolve_template_repo_full_name(validated_key)
        return default_repo

    if template_repo:
        return template_repo

    if validated_key:
        return resolve_template_repo_full_name(validated_key)
    return None
