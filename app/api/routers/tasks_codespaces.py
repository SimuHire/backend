"""Aggregated tasks router (codespaces, runs, submissions)."""

from fastapi import APIRouter

from app.api.dependencies.github_native import get_actions_runner, get_github_client
from app.api.routers.tasks import init as init_route
from app.api.routers.tasks import poll, run, status, submit
from app.api.routers.tasks import router as tasks_router
from app.api.routers.tasks.helpers import (
    _compute_current_task,
    _concurrency_guard,
    _rate_limit_or_429,
)
from app.core.auth import rate_limit
from app.core.settings import settings
from app.domains.candidate_sessions import service as cs_service
from app.domains.submissions import rate_limits as submissions_rate_limits
from app.domains.submissions import service_candidate as submission_service

router = APIRouter()
router.include_router(tasks_router)

# Legacy aliases for tests/overrides
init_codespace = init_route.init_codespace_route
codespace_status = status.codespace_status_route
run_task_tests = run.run_task_tests_route
get_run_result = poll.get_run_result_route
submit_task = submit.submit_task_route
workspace_repo = submission_service.workspace_repo
_RATE_LIMIT_RULE = submissions_rate_limits._DEFAULT_RATE_LIMIT_RULES

__all__ = [
    "router",
    "get_actions_runner",
    "get_github_client",
    "init_codespace",
    "codespace_status",
    "run_task_tests",
    "get_run_result",
    "submit_task",
    "submission_service",
    "workspace_repo",
    "cs_service",
    "_rate_limit_or_429",
    "_concurrency_guard",
    "_compute_current_task",
    "settings",
    "rate_limit",
    "_RATE_LIMIT_RULE",
]
