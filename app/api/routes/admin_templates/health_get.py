from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.github_native import get_github_client
from app.domains.github_native import GithubClient
from app.domains.github_native.template_health import (
    TemplateHealthResponse,
    check_template_health,
)
from app.infra.config import settings
from app.infra.security.admin_api_key import require_admin_key

router = APIRouter()


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
