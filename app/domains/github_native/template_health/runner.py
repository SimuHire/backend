from __future__ import annotations

from app.domains.github_native import GithubClient
from app.domains.github_native.template_health.repo_check import check_template_repo
from app.domains.github_native.template_health.runner_concurrency import (
    run_with_concurrency,
)
from app.domains.github_native.template_health.schemas import (
    RunMode,
    TemplateHealthResponse,
)
from app.domains.tasks.template_catalog import TEMPLATE_CATALOG


async def check_template_health(
    github_client: GithubClient,
    *,
    workflow_file: str,
    mode: RunMode = "static",
    template_keys: list[str] | None = None,
    timeout_seconds: int = 180,
    concurrency: int = 1,
) -> TemplateHealthResponse:
    selected = template_keys or list(TEMPLATE_CATALOG.keys())
    items = await run_with_concurrency(
        selected,
        concurrency=concurrency,
        worker=lambda key: check_template_repo(
            github_client,
            template_key=key,
            repo_full_name=TEMPLATE_CATALOG[key]["repo_full_name"],
            workflow_file=workflow_file,
            mode=mode,
            timeout_seconds=timeout_seconds,
        ),
    )
    return TemplateHealthResponse(ok=all(item.ok for item in items), templates=items, mode=mode)
