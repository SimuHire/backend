"""Logic helper for current task route."""

from app.api.routes.candidate_sessions_routes.rate_limits import (
    CANDIDATE_CURRENT_TASK_RATE_LIMIT,
)
from app.api.routes.candidate_sessions_routes.responses import (
    build_current_task_response,
)
from app.api.routes.candidate_sessions_routes.time_utils import utcnow
from app.domains.candidate_sessions import service as cs_service
from app.infra.security import rate_limit


async def build_current_task_view(candidate_session_id, request, principal, db):
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key(
            "candidate_current_task",
            str(candidate_session_id),
            rate_limit.client_id(request),
        )
        rate_limit.limiter.allow(key, CANDIDATE_CURRENT_TASK_RATE_LIMIT)
    now = utcnow()
    cs = await cs_service.fetch_owned_session(
        db, candidate_session_id, principal, now=now
    )
    (
        _tasks,
        completed_ids,
        current_task,
        completed,
        total,
        is_complete,
    ) = await cs_service.progress_snapshot(db, cs)
    if is_complete and cs.status != "completed":
        cs.status = "completed"
        if cs.completed_at is None:
            cs.completed_at = now
        await db.commit()
        await db.refresh(cs)
    return build_current_task_response(
        cs, current_task, completed_ids, completed, total, is_complete
    )


__all__ = ["build_current_task_view"]
