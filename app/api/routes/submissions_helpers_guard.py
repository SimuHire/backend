from __future__ import annotations

from app.infra.security.roles import ensure_recruiter


def ensure_recruiter_guard(user):
    try:
        from app.api.routes import submissions as submissions_routes
    except Exception:
        return ensure_recruiter(user)
    return getattr(submissions_routes, "ensure_recruiter", ensure_recruiter)(user)


__all__ = ["ensure_recruiter_guard"]
