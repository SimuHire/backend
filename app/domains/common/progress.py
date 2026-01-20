from __future__ import annotations

from app.domains.common.base import APIModel


class ProgressSummary(APIModel):
    """Shared progress summary schema."""

    completed: int
    total: int
