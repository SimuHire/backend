from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.github_native import get_github_client
from app.domains.common.base import APIModel
from app.domains.github_native import GithubClient
from app.domains.github_native.template_health import (
    TemplateHealthResponse,
    check_template_health,
)
from app.domains.tasks.template_catalog import (
    ALLOWED_TEMPLATE_KEYS,
    validate_template_key,
)
from app.infra.config import settings
from app.infra.security.admin_api_key import require_admin_key

router = APIRouter()
MAX_LIVE_TEMPLATE_KEYS = 5


@router.get(
    "/templates/health",
    response_model=TemplateHealthResponse,
    status_code=status.HTTP_200_OK,
)
async def get_template_health(
    _: Annotated[None, Depends(require_admin_key)],
    github_client: Annotated[GithubClient, Depends(get_github_client)],
    mode: Literal["static", "live"] = "static",
) -> TemplateHealthResponse:
    """Check template repos against the Actions artifact contract (admin-only)."""
    if mode != "static":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /api/admin/templates/health/run for live checks",
        )
    return await check_template_health(
        github_client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        mode="static",
    )


class TemplateHealthRunRequest(APIModel):
    """Request payload for live template health checks."""

    templateKeys: list[str]
    mode: Literal["live", "static"] = "live"
    timeoutSeconds: int = 180
    concurrency: int = 2


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
    """Run opt-in template health checks."""
    if payload.mode != "live":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only live mode is supported for this endpoint",
        )
    if not payload.templateKeys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="templateKeys is required",
        )
    if len(payload.templateKeys) > MAX_LIVE_TEMPLATE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"templateKeys must include {MAX_LIVE_TEMPLATE_KEYS} or fewer items",
        )
    invalid = [key for key in payload.templateKeys if key not in ALLOWED_TEMPLATE_KEYS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid templateKeys: {', '.join(invalid)}",
        )
    template_keys = [validate_template_key(key) for key in payload.templateKeys]
    timeout_seconds = max(1, min(payload.timeoutSeconds, 600))
    concurrency = max(1, min(payload.concurrency, 5))
    return await check_template_health(
        github_client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        mode="live",
        template_keys=template_keys,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
    )
