from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.service.claims import claim_invite_with_principal
from app.domains.candidate_sessions.service.email import (
    normalize_email as _normalize_email,
)
from app.domains.candidate_sessions.service.fetch import (
    fetch_by_token,
    fetch_by_token_for_update,
    fetch_owned_session,
)
from app.domains.candidate_sessions.service.invites import invite_list_for_principal
from app.domains.candidate_sessions.service.ownership import (
    ensure_candidate_ownership as _ensure_candidate_ownership,
)
from app.domains.candidate_sessions.service.progress import (
    completed_task_ids,
    load_tasks,
    progress_snapshot,
)
from app.domains.candidate_sessions.service.status import (
    mark_in_progress,
    require_not_expired,
)

__all__ = [
    "cs_repo",
    "claim_invite_with_principal",
    "completed_task_ids",
    "fetch_by_token",
    "fetch_by_token_for_update",
    "fetch_owned_session",
    "invite_list_for_principal",
    "load_tasks",
    "mark_in_progress",
    "progress_snapshot",
    "require_not_expired",
    "_normalize_email",
    "_ensure_candidate_ownership",
]
