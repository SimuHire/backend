from __future__ import annotations

from typing import Any

DEFAULT_TEMPLATE_KEY = "python-fastapi"
CATALOG_ENTRIES: list[tuple[str, str, str]] = [
    ("python-fastapi", "tenon-hire-dev/tenon-template-python-fastapi", "Python (FastAPI)"),
    ("node-express-ts", "tenon-hire-dev/tenon-template-node-express-ts", "Node.js (Express, TS)"),
    ("node-nest-ts", "tenon-hire-dev/tenon-template-node-nest-ts", "Node.js (NestJS, TS)"),
    ("java-springboot", "tenon-hire-dev/tenon-template-java-springboot", "Java (Spring Boot)"),
    ("go-gin", "tenon-hire-dev/tenon-template-go-gin", "Go (Gin)"),
    ("dotnet-webapi", "tenon-hire-dev/tenon-template-dotnet-webapi", ".NET (Web API)"),
    ("monorepo-nextjs-nest", "tenon-hire-dev/tenon-template-monorepo-nextjs-nest", "Monorepo (Next.js + NestJS)"),
    ("monorepo-nextjs-fastapi", "tenon-hire-dev/tenon-template-monorepo-nextjs-fastapi", "Monorepo (Next.js + FastAPI)"),
    ("monorepo-react-express", "tenon-hire-dev/tenon-template-monorepo-react-express", "Monorepo (React + Express)"),
    ("monorepo-react-springboot", "tenon-hire-dev/tenon-template-monorepo-react-springboot", "Monorepo (React + Spring Boot)"),
    ("mobile-fullstack-expo-fastapi", "tenon-hire-dev/tenon-template-monorepo-expo-fastapi", "Mobile Fullstack (Expo + FastAPI)"),
    ("mobile-backend-fastapi", "tenon-hire-dev/tenon-template-mobile-backend-fastapi", "Mobile Backend (FastAPI)"),
    ("ml-backend-fastapi", "tenon-hire-dev/tenon-template-ml-backend-fastapi", "ML Backend (FastAPI)"),
    ("ml-infra-mlops", "tenon-hire-dev/tenon-template-ml-infra-mlops", "ML Infra / MLOps"),
]

TEMPLATE_CATALOG: dict[str, dict[str, Any]] = {
    key: {"repo_full_name": repo_full_name, "display_name": display_name}
    for key, repo_full_name, display_name in CATALOG_ENTRIES
}
ALLOWED_TEMPLATE_KEYS: set[str] = set(TEMPLATE_CATALOG.keys())
LEGACY_TEMPLATE_REPO_REWRITES: dict[str, str] = {
    "tenon-templates/node-day2-api": TEMPLATE_CATALOG[DEFAULT_TEMPLATE_KEY]["repo_full_name"],
    "tenon-templates/node-day3-debug": TEMPLATE_CATALOG[DEFAULT_TEMPLATE_KEY]["repo_full_name"],
    "tenon-dev/tenon-template-python": TEMPLATE_CATALOG["python-fastapi"]["repo_full_name"],
}

__all__ = [
    "DEFAULT_TEMPLATE_KEY",
    "CATALOG_ENTRIES",
    "TEMPLATE_CATALOG",
    "ALLOWED_TEMPLATE_KEYS",
    "LEGACY_TEMPLATE_REPO_REWRITES",
]
