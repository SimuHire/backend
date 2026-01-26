from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies.github_native import get_github_client
from app.api.routers.admin_templates.schemas import TemplateHealthRunRequest
from app.api.routers.admin_templates.validation import validate_live_request
from app.core.auth.admin_api_key import require_admin_key
from app.core.settings import settings
from app.integrations.github import GithubClient
from app.integrations.github.template_health import (
    TemplateHealthResponse,
    check_template_health,
)

router = APIRouter()


@router.post(
    "/templates/health/run",
    response_model=TemplateHealthResponse,
    status_code=status.HTTP_200_OK,
)
async def run_template_health(
    payload: TemplateHealthRunRequest,
    _: Annotated[None, Depends(require_admin_key)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> TemplateHealthResponse:
    template_keys, timeout_seconds, concurrency = validate_live_request(payload)
    return await check_template_health(
        github_client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        mode="live",
        template_keys=template_keys,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
    )
