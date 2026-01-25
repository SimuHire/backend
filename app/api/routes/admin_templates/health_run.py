from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies.github_native import get_github_client
from app.api.routes.admin_templates.schemas import TemplateHealthRunRequest
from app.api.routes.admin_templates.validation import validate_live_request
from app.domains.github_native import GithubClient
from app.domains.github_native.template_health import (
    TemplateHealthResponse,
    check_template_health,
)
from app.infra.config import settings
from app.infra.security.admin_api_key import require_admin_key

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
