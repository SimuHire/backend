from __future__ import annotations

from app.domains.tasks import template_catalog
from app.infra.config import settings


def _resolver():
    try:
        from app.domains.simulations import service as sim_service

        return getattr(
            sim_service,
            "resolve_template_repo_full_name",
            template_catalog.resolve_template_repo_full_name,
        )
    except Exception:
        return template_catalog.resolve_template_repo_full_name


def _template_repo_for_task(
    day_index: int, task_type: str, template_key: str
) -> str | None:
    task_type = (task_type or "").lower()
    if task_type not in {"code", "debug"}:
        return None
    if day_index not in {2, 3}:
        return _resolver()(template_key)

    repo = _resolver()(template_key)
    if "/" not in repo and settings.github.GITHUB_TEMPLATE_OWNER:
        return f"{settings.github.GITHUB_TEMPLATE_OWNER}/{repo}"
    return repo
