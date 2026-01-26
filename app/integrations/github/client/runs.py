from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkflowRun:
    """Normalized workflow run information."""

    id: int
    status: str
    conclusion: str | None
    html_url: str | None
    head_sha: str | None
    artifact_count: int | None = None
    event: str | None = None
    created_at: str | None = None


def parse_run(payload: dict[str, Any]) -> WorkflowRun:
    return WorkflowRun(
        id=int(payload.get("id") or 0),
        status=str(payload.get("status") or ""),
        conclusion=payload.get("conclusion"),
        html_url=payload.get("html_url"),
        head_sha=payload.get("head_sha"),
        artifact_count=payload.get("artifacts") or payload.get("artifacts_count"),
        event=payload.get("event"),
        created_at=payload.get("created_at"),
    )
