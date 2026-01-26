from __future__ import annotations

from app.core.auth.roles import ensure_recruiter


def ensure_recruiter_guard(user):
    try:
        from app.api.routers import submissions as submissions_routes
    except Exception:
        return ensure_recruiter(user)
    return getattr(submissions_routes, "ensure_recruiter", ensure_recruiter)(user)


__all__ = ["ensure_recruiter_guard"]
