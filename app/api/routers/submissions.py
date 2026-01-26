"""Aggregated recruiter submissions router."""

from fastapi import APIRouter

from app.api.routers.submissions_helpers import (
    get_submission_detail,
    list_submissions,
)
from app.api.routers.submissions_routes import router as submissions_router
from app.core.auth.roles import ensure_recruiter
from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.presenter import build_diff_url as _build_diff_url
from app.domains.submissions.presenter import (
    build_test_results as _build_test_results,
)
from app.domains.submissions.presenter import (
    parse_diff_summary as _parse_diff_summary,
)
from app.domains.submissions.presenter import (
    redact_text as _redact_text,
)
from app.domains.submissions.presenter import (
    truncate_output as _truncate_output,
)

router = APIRouter()
router.include_router(submissions_router)
_derive_test_status = recruiter_sub_service.derive_test_status


__all__ = [
    "router",
    "_build_test_results",
    "_parse_diff_summary",
    "_build_diff_url",
    "_redact_text",
    "_truncate_output",
    "_derive_test_status",
    "recruiter_sub_service",
    "ensure_recruiter",
    "get_submission_detail",
    "list_submissions",
]
